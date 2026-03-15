#!/usr/bin/env python3
"""Sign and verify release checklist using SHA256 or HMAC-SHA256."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_PATH = ROOT / "docs" / "perf" / "RELEASE_CHECKLIST.md"
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
SIGNATURE_PATH = RESULTS_DIR / "release-checklist-signature.json"
REPORT_MD = ROOT / "docs" / "perf" / "SIGNED_RELEASE_CHECKLIST.md"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def make_signature(content: bytes, key: str | None) -> tuple[str, str]:
    if key:
        sig = hmac.new(key.encode("utf-8"), content, hashlib.sha256).hexdigest()
        return "hmac-sha256", sig
    return "sha256", digest(content)


def sign(signer: str, key: str | None) -> int:
    if not CHECKLIST_PATH.exists():
        print(f"Missing checklist: {CHECKLIST_PATH}")
        return 2
    content = CHECKLIST_PATH.read_bytes()
    checksum = digest(content)
    method, signature = make_signature(content, key)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signer": signer,
        "method": method,
        "checklist_sha256": checksum,
        "signature": signature,
        "checklist_path": str(CHECKLIST_PATH.relative_to(ROOT)),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SIGNATURE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report = "\n".join(
        [
            "# Signed Release Checklist",
            "",
            f"Generated at: `{payload['generated_at']}`",
            f"Signer: `{payload['signer']}`",
            f"Method: `{payload['method']}`",
            f"Checklist SHA256: `{payload['checklist_sha256']}`",
            f"Signature: `{payload['signature']}`",
            "",
            "## Source",
            "",
            f"- Checklist: `{payload['checklist_path']}`",
            f"- Signature JSON: `{SIGNATURE_PATH.relative_to(ROOT).as_posix()}`",
        ]
    )
    REPORT_MD.write_text(report, encoding="utf-8")
    print(f"Wrote {SIGNATURE_PATH}")
    print(f"Wrote {REPORT_MD}")
    return 0


def verify(key: str | None) -> int:
    if not SIGNATURE_PATH.exists() or not CHECKLIST_PATH.exists():
        print("Missing signature or checklist file.")
        return 2
    payload = json.loads(SIGNATURE_PATH.read_text(encoding="utf-8"))
    content = CHECKLIST_PATH.read_bytes()
    checksum = digest(content)
    method = payload.get("method")
    expected_sig = payload.get("signature")
    if method == "hmac-sha256":
        if not key:
            print("Verification requires RELEASE_SIGNING_KEY for hmac-sha256.")
            return 2
        _, computed_sig = make_signature(content, key)
    else:
        _, computed_sig = make_signature(content, None)
    ok = checksum == payload.get("checklist_sha256") and expected_sig == computed_sig
    print("Verification:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign/verify release checklist.")
    parser.add_argument("--signer", default=os.getenv("RELEASE_SIGNER", "unknown"))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    key = os.getenv("RELEASE_SIGNING_KEY")
    if args.verify:
        return verify(key)
    return sign(args.signer, key)


if __name__ == "__main__":
    raise SystemExit(main())
