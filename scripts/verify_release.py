#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

MANIFEST_NAME = "RELEASE_MANIFEST.json"
EXPECTED_PRODUCT = "DataVision AI"
EXPECTED_FORMAT = "reproducible-source-archive-v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def verify_archive(archive: Path, sha_file: Path | None = None) -> dict:
    archive = Path(archive)
    if not archive.is_file():
        raise ValueError(f"Archive absente: {archive}")

    if sha_file is not None:
        expected = Path(sha_file).read_text(encoding="utf-8").split()[0].lower()
        actual = sha256(archive).lower()
        if actual != expected:
            raise ValueError(f"SHA256 invalide: {actual} != {expected}")

    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"Archive corrompue: {bad}")

        infos = [info for info in zf.infolist() if not info.is_dir()]
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Archive invalide: entrées ZIP dupliquées")
        unsafe = [name for name in names if not _safe_member(name)]
        if unsafe:
            raise ValueError(f"Archive invalide: chemin dangereux {unsafe[0]}")

        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise ValueError("Archive invalide: plusieurs racines top-level")
        root_name = next(iter(roots))
        manifest_path = f"{root_name}/{MANIFEST_NAME}"
        if manifest_path not in names:
            raise ValueError(f"Manifest embarqué absent: {manifest_path}")

        try:
            manifest = json.loads(zf.read(manifest_path).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Manifest embarqué invalide: {exc}") from exc

        if manifest.get("product") != EXPECTED_PRODUCT:
            raise ValueError(f"Produit inattendu dans le manifest: {manifest.get('product')!r}")
        if manifest.get("format") != EXPECTED_FORMAT:
            raise ValueError(f"Format de manifest inattendu: {manifest.get('format')!r}")
        version = str(manifest.get("version", "")).strip()
        if not version:
            raise ValueError("Version absente du manifest")
        expected_root = f"datavision-ai-v{version}-complet"
        if root_name != expected_root:
            raise ValueError(f"Racine archive {root_name!r}, attendue {expected_root!r}")

        rows = manifest.get("files")
        if not isinstance(rows, list):
            raise ValueError("Manifest invalide: files doit être une liste")

        declared: dict[str, dict] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Manifest invalide: entrée files non objet")
            rel = str(row.get("path", ""))
            if not rel or not _safe_member(rel) or PurePosixPath(rel).parts[0] == root_name:
                raise ValueError(f"Manifest invalide: chemin relatif {rel!r}")
            if rel == MANIFEST_NAME:
                raise ValueError("Le manifest ne doit pas se déclarer lui-même")
            if rel in declared:
                raise ValueError(f"Manifest invalide: fichier déclaré deux fois: {rel}")
            declared[rel] = row

        actual_rel = {
            str(PurePosixPath(name).relative_to(root_name))
            for name in names
            if name != manifest_path
        }
        declared_rel = set(declared)
        missing = sorted(declared_rel - actual_rel)
        extra = sorted(actual_rel - declared_rel)
        if missing:
            raise ValueError(f"Fichier déclaré absent du ZIP: {missing[0]}")
        if extra:
            raise ValueError(f"Fichier ZIP non déclaré dans le manifest: {extra[0]}")

        for rel, row in declared.items():
            data = zf.read(f"{root_name}/{rel}")
            expected_size = row.get("size")
            expected_hash = str(row.get("sha256", "")).lower()
            if expected_size != len(data):
                raise ValueError(f"Taille invalide pour {rel}: {len(data)} != {expected_size}")
            actual_hash = sha256_bytes(data)
            if actual_hash != expected_hash:
                raise ValueError(f"SHA256 fichier invalide pour {rel}: {actual_hash} != {expected_hash}")

    return {
        "product": EXPECTED_PRODUCT,
        "version": version,
        "root": root_name,
        "files": len(declared),
        "sha256": sha256(archive),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("--sha-file")
    args = parser.parse_args()
    try:
        result = verify_archive(
            Path(args.archive),
            Path(args.sha_file) if args.sha_file else None,
        )
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"release verification: FAIL - {exc}")
        return 1
    print(
        "release verification: OK "
        f"(v{result['version']}, {result['files']} files, sha256={result['sha256']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
