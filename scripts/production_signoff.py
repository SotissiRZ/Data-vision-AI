#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

REQUIRED_KINDS = ("ci", "compose", "helm", "e2e", "load", "security", "uat")
VALID_STATUS = {"pass", "fail", "waived"}
EVIDENCE_SCHEMA = "datavision-production-evidence-v1"
SIGNOFF_SCHEMA = "datavision-production-signoff-v2"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def project_version() -> str:
    path = Path(__file__).resolve().parents[1] / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else "unknown"


def _parse_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def record(args: argparse.Namespace) -> int:
    if args.kind not in REQUIRED_KINDS:
        raise SystemExit(f"Unknown evidence kind: {args.kind}")
    if args.status not in VALID_STATUS:
        raise SystemExit(f"Invalid status: {args.status}")
    evidence_dir = Path(args.evidence_dir).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    attachments = []
    for raw in args.attachment or []:
        path = Path(raw).resolve()
        if not path.is_file():
            raise SystemExit(f"Attachment not found: {path}")
        attachments.append({"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size})
    payload = {
        "schema": EVIDENCE_SCHEMA,
        "product_version": project_version(),
        "kind": args.kind,
        "status": args.status,
        "recorded_at": utc_now(),
        "source": args.source,
        "actor": args.actor,
        "details": args.details or "",
        "attachments": attachments,
    }
    payload["evidence_sha256"] = sha256_json(payload)
    output = evidence_dir / f"{args.kind}.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


def _verify_attachment(item: dict) -> tuple[bool, str | None]:
    raw_path = str(item.get("path") or "").strip()
    expected_sha = str(item.get("sha256") or "").strip().lower()
    expected_size = item.get("size")
    if not raw_path or not expected_sha:
        return False, "attachment metadata incomplete"
    path = Path(raw_path)
    if not path.is_file():
        return False, f"attachment missing: {raw_path}"
    if expected_size is not None and path.stat().st_size != int(expected_size):
        return False, f"attachment size mismatch: {raw_path}"
    if sha256_file(path) != expected_sha:
        return False, f"attachment sha256 mismatch: {raw_path}"
    return True, None


def _verify_evidence_payload(kind: str, payload: dict, *, allow_waivers: bool) -> tuple[bool, list[str]]:
    errors: list[str] = []
    status = payload.get("status")
    if payload.get("schema") != EVIDENCE_SCHEMA:
        errors.append("invalid evidence schema")
    if payload.get("kind") != kind:
        errors.append("kind mismatch")
    if payload.get("product_version") != project_version():
        errors.append("product version mismatch")
    if status not in VALID_STATUS:
        errors.append("invalid status")
    elif status == "waived" and not allow_waivers:
        errors.append("waiver not accepted in strict sign-off")
    elif status == "fail":
        errors.append("evidence status is fail")
    if not str(payload.get("source") or "").strip():
        errors.append("missing source")
    if not str(payload.get("actor") or "").strip():
        errors.append("missing actor")
    if not _parse_timestamp(payload.get("recorded_at")):
        errors.append("invalid recorded_at")
    claimed_hash = str(payload.get("evidence_sha256") or "").strip().lower()
    if not claimed_hash:
        errors.append("missing evidence_sha256")
    else:
        material = dict(payload)
        material.pop("evidence_sha256", None)
        if sha256_json(material) != claimed_hash:
            errors.append("evidence_sha256 mismatch")
    for attachment in payload.get("attachments") or []:
        ok, error = _verify_attachment(attachment)
        if not ok and error:
            errors.append(error)
    return not errors, errors


def verify(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.evidence_dir).resolve()
    rows: list[dict] = []
    digest_material: list[dict] = []
    for kind in REQUIRED_KINDS:
        path = evidence_dir / f"{kind}.json"
        if not path.is_file():
            rows.append({"kind": kind, "status": "missing", "ok": False, "errors": ["evidence file missing"]})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rows.append({"kind": kind, "status": "invalid", "ok": False, "errors": [str(exc)]})
            continue
        ok, errors = _verify_evidence_payload(kind, payload, allow_waivers=bool(args.allow_waivers))
        row = {
            "kind": kind,
            "status": payload.get("status"),
            "ok": ok,
            "recorded_at": payload.get("recorded_at"),
            "source": payload.get("source"),
            "actor": payload.get("actor"),
            "evidence_sha256": payload.get("evidence_sha256"),
            "errors": errors,
        }
        rows.append(row)
        digest_material.append({"kind": kind, "evidence_sha256": payload.get("evidence_sha256")})
    all_present = all(row["status"] != "missing" for row in rows)
    all_acceptable = all(row["ok"] for row in rows)
    summary = {
        "schema": SIGNOFF_SCHEMA,
        "product_version": project_version(),
        "generated_at": utc_now(),
        "status": "pass" if all_acceptable else "pending",
        "strict": not bool(args.allow_waivers),
        "all_required_evidence_present": all_present,
        "all_required_evidence_acceptable": all_acceptable,
        "evidence_digest_sha256": sha256_json(digest_material),
        "evidence": rows,
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output = evidence_dir / "production-signoff.json"
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.require_all and not all_acceptable:
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Record and verify target production acceptance evidence.")
    sub = ap.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--evidence-dir", default="production-evidence")
    rec.add_argument("--kind", required=True, choices=REQUIRED_KINDS)
    rec.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    rec.add_argument("--source", required=True)
    rec.add_argument("--actor", default="operator")
    rec.add_argument("--details")
    rec.add_argument("--attachment", action="append")
    rec.set_defaults(func=record)

    ver = sub.add_parser("verify")
    ver.add_argument("--evidence-dir", default="production-evidence")
    ver.add_argument("--require-all", action="store_true")
    ver.add_argument("--allow-waivers", action="store_true", help="Accept explicit waivers; strict release sign-off should omit this flag.")
    ver.set_defaults(func=verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
