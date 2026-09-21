from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from app.core.config import get_settings
from app.services.metadata_store import execute, get_engine, init_metadata_store, json_dumps
from app.services.schema_migrations import migration_status


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _backup_dir() -> Path:
    path = get_settings().data_root / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _database_cli_connection() -> tuple[str, dict[str, str]]:
    url = get_engine().url
    cli_url = url.set(drivername="postgresql", password=None).render_as_string(hide_password=False)
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return cli_url, env


def _record(run_id: str, **values: Any) -> None:
    init_metadata_store()
    columns = ["id"] + list(values)
    placeholders = [":id"] + [f":{k}" for k in values]
    params = {"id": run_id, **values}
    execute(f"INSERT INTO backup_runs({','.join(columns)}) VALUES({','.join(placeholders)})", params)


def _update(run_id: str, **values: Any) -> None:
    setters = ",".join(f"{key}=:{key}" for key in values)
    execute(f"UPDATE backup_runs SET {setters} WHERE id=:id", {"id": run_id, **values})


def object_store_status() -> dict[str, Any]:
    settings = get_settings()
    provider = settings.backup_object_store_provider.strip().lower()
    if provider == "disabled":
        return {"enabled": False, "provider": "disabled", "configured": True}
    if provider != "s3_compatible":
        return {"enabled": True, "provider": provider, "configured": False, "error": "Provider non supporté"}
    parsed = urlparse(settings.backup_object_store_endpoint)
    configured = bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and settings.backup_object_store_bucket.strip()
        and settings.backup_object_store_access_key.strip()
        and settings.backup_object_store_secret_key.strip()
    )
    return {
        "enabled": True,
        "provider": "s3_compatible",
        "configured": configured,
        "endpoint": settings.backup_object_store_endpoint,
        "bucket": settings.backup_object_store_bucket,
        "prefix": settings.backup_object_store_prefix.strip("/"),
        "region": settings.backup_object_store_region,
        "auto_upload": settings.backup_object_store_auto_upload,
        "verify_tls": settings.backup_object_store_verify_tls,
    }


def _s3_signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    k_date = hmac.new(("AWS4" + secret).encode(), date_stamp.encode(), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _s3_request(method: str, key: str, *, body: bytes = b"", extra_headers: dict[str, str] | None = None) -> Any:
    settings = get_settings()
    status = object_store_status()
    if not status.get("enabled") or not status.get("configured"):
        raise RuntimeError("Le stockage objet S3-compatible n'est pas configuré")
    endpoint = settings.backup_object_store_endpoint.rstrip("/")
    bucket = settings.backup_object_store_bucket.strip()
    normalized_key = key.strip("/")
    canonical_uri = "/" + quote(bucket, safe="") + "/" + quote(normalized_key, safe="/~")
    url = endpoint + canonical_uri
    parsed = urlparse(url)
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = settings.backup_object_store_region or "us-east-1"
    payload_hash = _bytes_sha256(body)
    headers: dict[str, str] = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if settings.backup_object_store_session_token:
        headers["x-amz-security-token"] = settings.backup_object_store_session_token
    for key_name, value in (extra_headers or {}).items():
        headers[key_name.lower()] = str(value).strip()
    canonical_header_names = sorted(headers)
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in canonical_header_names)
    signed_headers = ";".join(canonical_header_names)
    canonical_request = "\n".join([method.upper(), canonical_uri, "", canonical_headers, signed_headers, payload_hash])
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()])
    signature = hmac.new(
        _s3_signing_key(settings.backup_object_store_secret_key, date_stamp, region),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={settings.backup_object_store_access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    import httpx

    response = httpx.request(
        method.upper(),
        url,
        content=body if method.upper() in {"PUT", "POST"} else None,
        headers=headers,
        timeout=30.0,
        verify=settings.backup_object_store_verify_tls,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"S3-compatible {method.upper()} a échoué ({response.status_code}): {response.text[:300]}")
    return response


def _object_key(path: Path) -> str:
    settings = get_settings()
    prefix = settings.backup_object_store_prefix.strip("/")
    return f"{prefix}/{path.name}" if prefix else path.name


def upload_backup_to_object_store(archive: Path) -> dict[str, Any]:
    archive = archive.resolve()
    if not archive.is_file():
        raise FileNotFoundError(archive.name)
    key = _object_key(archive)
    digest = _sha256(archive)
    response = _s3_request(
        "PUT",
        key,
        body=archive.read_bytes(),
        extra_headers={"content-type": "application/gzip", "x-amz-meta-sha256": digest},
    )
    bucket = get_settings().backup_object_store_bucket.strip()
    return {
        "key": key,
        "uri": f"s3://{bucket}/{key}",
        "sha256": digest,
        "etag": response.headers.get("etag", "").strip('"'),
    }


def download_backup_from_object_store(key: str, *, destination: Path | None = None) -> Path:
    key = key.strip("/")
    if not key or ".." in Path(key).parts:
        raise ValueError("Clé objet invalide")
    response = _s3_request("GET", key)
    target = (destination or (_backup_dir() / Path(key).name)).resolve()
    if _backup_dir() not in target.parents:
        raise PermissionError("La destination doit rester dans le répertoire de sauvegarde DataVision")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    return target


def _manifest_entry(path: Path, arcname: str) -> dict[str, Any]:
    return {"path": arcname, "sha256": _sha256(path), "size_bytes": path.stat().st_size}


def create_backup(*, label: str = "manual") -> dict[str, Any]:
    settings = get_settings()
    init_metadata_store()
    migrations = migration_status()
    if not migrations.get("ready"):
        raise RuntimeError(f"Migrations en attente: {migrations.get('pending')}")

    run_id = str(uuid.uuid4())
    started = _utcnow()
    engine = get_engine()
    backend = engine.dialect.name
    safe_label = "".join(ch for ch in label.lower() if ch.isalnum() or ch in "-_")[:32] or "backup"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = _backup_dir() / f"datavision-{stamp}-{safe_label}-{run_id[:8]}.tar.gz"
    _record(
        run_id,
        status="running",
        kind=safe_label,
        archive_path=str(archive),
        sha256=None,
        database_backend=backend,
        size_bytes=None,
        started_at=started,
        completed_at=None,
        details_json=json_dumps({"migration": migrations.get("current")}),
        object_uri=None,
        object_key=None,
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="datavision-backup-"))
    try:
        db_dump: Path | None = None
        if backend == "postgresql":
            pg_dump = shutil.which("pg_dump")
            if not pg_dump and settings.backup_require_database_dump:
                raise RuntimeError("pg_dump est requis pour une sauvegarde PostgreSQL complète")
            if pg_dump:
                db_dump = tmp_dir / "database.dump"
                cli_url, cli_env = _database_cli_connection()
                subprocess.run(
                    [pg_dump, "--format=custom", "--no-owner", f"--file={db_dump}", cli_url],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=cli_env,
                )
        elif backend != "sqlite":
            raise RuntimeError(f"Backend metadata non supporté pour sauvegarde: {backend}")

        data_root = settings.data_root.resolve()
        backup_root = _backup_dir()
        files: list[tuple[Path, str]] = []
        if db_dump:
            files.append((db_dump, "database.dump"))
        if data_root.exists():
            for path in sorted(data_root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                resolved = path.resolve()
                if backup_root == resolved or backup_root in resolved.parents:
                    continue
                files.append((path, f"data/{path.relative_to(data_root).as_posix()}"))

        manifest = {
            "format": "datavision-backup-v2",
            "product_version": "2.60.0",
            "backup_id": run_id,
            "created_at": _utcnow(),
            "database_backend": backend,
            "schema_migration": migrations.get("current"),
            "database_dump": "database.dump" if db_dump else None,
            "data_prefix": "data/",
            "files": [_manifest_entry(path, arcname) for path, arcname in files],
        }
        manifest_path = tmp_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with tarfile.open(archive, "w:gz") as tf:
            tf.add(manifest_path, arcname="manifest.json", recursive=False)
            for path, arcname in files:
                tf.add(path, arcname=arcname, recursive=False)

        digest = _sha256(archive)
        object_result: dict[str, Any] | None = None
        if settings.backup_object_store_auto_upload and settings.backup_object_store_provider != "disabled":
            object_result = upload_backup_to_object_store(archive)
        completed = _utcnow()
        _update(
            run_id,
            status="completed",
            sha256=digest,
            size_bytes=archive.stat().st_size,
            completed_at=completed,
            object_uri=object_result.get("uri") if object_result else None,
            object_key=object_result.get("key") if object_result else None,
            details_json=json_dumps({"migration": migrations.get("current"), "manifest": manifest, "object_store": object_result}),
        )
        prune_backups(settings.backup_retention_count)
        return {
            "id": run_id,
            "status": "completed",
            "archive": str(archive),
            "sha256": digest,
            "size_bytes": archive.stat().st_size,
            "database_backend": backend,
            "created_at": completed,
            "object_store": object_result,
        }
    except Exception as exc:
        _update(run_id, status="failed", completed_at=_utcnow(), details_json=json_dumps({"error": str(exc)}))
        if archive.exists():
            archive.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def inspect_backup(archive: Path) -> dict[str, Any]:
    archive = archive.resolve()
    if _backup_dir() not in archive.parents:
        raise PermissionError("Archive hors du répertoire de sauvegarde DataVision")
    if not archive.is_file():
        raise FileNotFoundError(archive.name)
    with tarfile.open(archive, "r:gz") as tf:
        member = tf.getmember("manifest.json")
        handle = tf.extractfile(member)
        if handle is None:
            raise RuntimeError("Manifest de sauvegarde introuvable")
        manifest = json.loads(handle.read().decode("utf-8"))
    if manifest.get("format") not in {"datavision-backup-v1", "datavision-backup-v2"}:
        raise RuntimeError("Format de sauvegarde DataVision non reconnu")
    return {"archive": str(archive), "sha256": _sha256(archive), "manifest": manifest}


def _safe_extract(tf: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tf.getmembers():
        target = (destination / member.name).resolve()
        if destination != target and destination not in target.parents:
            raise RuntimeError("Archive de sauvegarde contenant un chemin non sûr")
        if member.issym() or member.islnk():
            raise RuntimeError("Les liens ne sont pas autorisés dans une sauvegarde DataVision")
    tf.extractall(destination, filter="data")


def _verify_manifest_files(staging: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    entries = manifest.get("files") or []
    if not entries:
        return {"hash_manifest": "legacy", "files_checked": 0}
    checked = 0
    for item in entries:
        rel = str(item.get("path") or "")
        expected = str(item.get("sha256") or "")
        target = (staging / rel).resolve()
        if staging.resolve() not in target.parents or not target.is_file():
            raise RuntimeError(f"Fichier de sauvegarde manquant: {rel}")
        if expected and _sha256(target) != expected:
            raise RuntimeError(f"Checksum invalide dans la sauvegarde: {rel}")
        checked += 1
    return {"hash_manifest": "passed", "files_checked": checked}


def latest_backup_archive() -> Path:
    files = sorted(_backup_dir().glob("datavision-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("Aucune sauvegarde DataVision disponible")
    return files[0]


def run_restore_drill(archive: Path) -> dict[str, Any]:
    init_metadata_store()
    inspected = inspect_backup(archive)
    manifest = inspected["manifest"]
    drill_id = str(uuid.uuid4())
    started = _utcnow()
    execute(
        "INSERT INTO restore_drills(id,backup_id,status,archive_sha256,checks_json,started_at,completed_at) "
        "VALUES(:id,:backup,'running',:sha,:checks,:started,NULL)",
        {"id": drill_id, "backup": manifest.get("backup_id"), "sha": inspected["sha256"], "checks": "{}", "started": started},
    )
    staging = Path(tempfile.mkdtemp(prefix="datavision-restore-drill-"))
    checks: dict[str, Any] = {"archive": "passed", "safe_extract": "pending", "database_dump": "not_required"}
    try:
        with tarfile.open(archive, "r:gz") as tf:
            _safe_extract(tf, staging)
        checks["safe_extract"] = "passed"
        checks.update(_verify_manifest_files(staging, manifest))
        if manifest.get("database_backend") == "postgresql" and manifest.get("database_dump"):
            dump = staging / str(manifest["database_dump"])
            if not dump.is_file():
                raise RuntimeError("Dump PostgreSQL absent du backup")
            pg_restore = shutil.which("pg_restore")
            if pg_restore:
                subprocess.run([pg_restore, "--list", str(dump)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                checks["database_dump"] = "pg_restore_list_passed"
            else:
                checks["database_dump"] = "present_pg_restore_unavailable"
        checks["file_count"] = sum(1 for p in staging.rglob("*") if p.is_file())
        execute(
            "UPDATE restore_drills SET status='passed',checks_json=:checks,completed_at=:completed WHERE id=:id",
            {"checks": json_dumps(checks), "completed": _utcnow(), "id": drill_id},
        )
        return {"id": drill_id, "status": "passed", "backup_id": manifest.get("backup_id"), "sha256": inspected["sha256"], "checks": checks}
    except Exception as exc:
        checks["error"] = str(exc)
        execute(
            "UPDATE restore_drills SET status='failed',checks_json=:checks,completed_at=:completed WHERE id=:id",
            {"checks": json_dumps(checks), "completed": _utcnow(), "id": drill_id},
        )
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restore_backup(archive: Path, *, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise PermissionError("Restauration refusée sans confirmation explicite")
    settings = get_settings()
    inspected = inspect_backup(archive)
    manifest = inspected["manifest"]
    staging = Path(tempfile.mkdtemp(prefix="datavision-restore-"))
    try:
        with tarfile.open(archive, "r:gz") as tf:
            _safe_extract(tf, staging)
        _verify_manifest_files(staging, manifest)
        data_src = staging / "data"
        data_root = settings.data_root.resolve()
        if data_src.exists():
            data_root.mkdir(parents=True, exist_ok=True)
            for src in sorted(data_src.rglob("*")):
                if not src.is_file():
                    continue
                rel = src.relative_to(data_src)
                if rel.parts and rel.parts[0] == "backups":
                    continue
                dst = data_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        if manifest.get("database_backend") == "postgresql" and manifest.get("database_dump"):
            pg_restore = shutil.which("pg_restore")
            if not pg_restore:
                raise RuntimeError("pg_restore est requis pour restaurer PostgreSQL")
            cli_url, cli_env = _database_cli_connection()
            subprocess.run(
                [pg_restore, "--clean", "--if-exists", "--no-owner", f"--dbname={cli_url}", str(staging / "database.dump")],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=cli_env,
            )
        return {"status": "restored", "backup_id": manifest.get("backup_id"), "sha256": inspected["sha256"]}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def prune_backups(retention_count: int) -> list[str]:
    keep = max(1, int(retention_count))
    files = sorted(_backup_dir().glob("datavision-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    deleted: list[str] = []
    for path in files[keep:]:
        path.unlink(missing_ok=True)
        deleted.append(path.name)
    return deleted
