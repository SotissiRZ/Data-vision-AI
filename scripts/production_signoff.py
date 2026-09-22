#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

REQUIRED_KINDS = ("ci", "compose", "helm", "e2e", "load", "security", "uat")
VALID_STATUS = {"pass", "fail", "waived"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "schema": "datavision-production-evidence-v1",
        "kind": args.kind,
        "status": args.status,
        "recorded_at": utc_now(),
        "source": args.source,
        "actor": args.actor,
        "details": args.details or "",
        "attachments": attachments,
    }
    output = evidence_dir / f"{args.kind}.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


def verify(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.evidence_dir).resolve()
    rows: list[dict] = []
    for kind in REQUIRED_KINDS:
        path = evidence_dir / f"{kind}.json"
        if not path.is_file():
            rows.append({"kind": kind, "status": "missing", "ok": False})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rows.append({"kind": kind, "status": "invalid", "ok": False, "error": str(exc)})
            continue
        status = payload.get("status")
        schema_ok = payload.get("schema") == "datavision-production-evidence-v1"
        rows.append({
            "kind": kind,
            "status": status,
            "ok": schema_ok and status in {"pass", "waived"},
            "recorded_at": payload.get("recorded_at"),
            "source": payload.get("source"),
        })
    all_present = all(row["status"] != "missing" for row in rows)
    all_acceptable = all(row["ok"] for row in rows)
    summary = {
        "schema": "datavision-production-signoff-v1",
        "generated_at": utc_now(),
        "status": "pass" if all_acceptable else "pending",
        "all_required_evidence_present": all_present,
        "all_required_evidence_acceptable": all_acceptable,
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
    ver.set_defaults(func=verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
