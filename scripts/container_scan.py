#!/usr/bin/env python3
"""Container hardening checks + optional Trivy base-image scan."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
REPORT_JSON = RESULTS_DIR / "container-scan.json"
REPORT_MD = ROOT / "docs" / "perf" / "CONTAINER_SCAN_REPORT.md"


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out.strip()


def parse_from_images(dockerfile: Path) -> list[str]:
    images: list[str] = []
    for line in dockerfile.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.upper().startswith("FROM "):
            continue
        parts = line.split()
        if len(parts) >= 2:
            images.append(parts[1])
    return images


def tag_pinned(image: str) -> bool:
    if "@sha256:" in image:
        return True
    if ":" not in image:
        return False
    tag = image.rsplit(":", 1)[-1]
    return tag != "latest"


def check_dockerfiles() -> dict:
    dockerfiles = sorted(ROOT.glob("**/Dockerfile"))
    entries = []
    for df in dockerfiles:
        rel = df.relative_to(ROOT).as_posix()
        images = parse_from_images(df)
        issues = []
        for image in images:
            if not tag_pinned(image):
                issues.append(f"unPinnedTag:{image}")
            if re.search(r":latest$", image):
                issues.append(f"latestTag:{image}")
        entries.append({"dockerfile": rel, "base_images": images, "issues": issues})
    return {"dockerfiles": entries}


def trivy_scan(images: list[str]) -> dict:
    if shutil.which("trivy") is None:
        return {"status": "tool_missing", "results": []}
    results = []
    for image in images:
        code, out = run(["trivy", "image", "--severity", "HIGH,CRITICAL", "--format", "json", image])
        if not out:
            results.append({"image": image, "status": "empty_output", "high_critical": 0})
            continue
        try:
            payload = json.loads(out)
            count = 0
            for r in payload.get("Results", []):
                for v in r.get("Vulnerabilities", []) or []:
                    sev = v.get("Severity", "")
                    if sev in {"HIGH", "CRITICAL"}:
                        count += 1
            results.append({"image": image, "status": "ok" if code in (0, 1) else "error", "high_critical": count})
        except json.JSONDecodeError:
            results.append({"image": image, "status": "parse_error", "high_critical": -1})
    return {"status": "ok", "results": results}


def main() -> int:
    docker_data = check_dockerfiles()
    base_images = sorted({img for d in docker_data["dockerfiles"] for img in d["base_images"]})
    trivy = trivy_scan(base_images)

    static_issues = sum(len(d["issues"]) for d in docker_data["dockerfiles"])
    trivy_findings = sum(max(0, r.get("high_critical", 0)) for r in trivy.get("results", []))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dockerfile_count": len(docker_data["dockerfiles"]),
        "static_policy_issues": static_issues,
        "trivy_status": trivy.get("status"),
        "trivy_high_critical_findings": trivy_findings,
        "dockerfiles": docker_data["dockerfiles"],
        "trivy_results": trivy.get("results", []),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Container Scan Report",
        "",
        f"Generated at: `{payload['generated_at']}`",
        f"Dockerfiles scanned: **{payload['dockerfile_count']}**",
        f"Static policy issues: **{payload['static_policy_issues']}**",
        f"Trivy status: `{payload['trivy_status']}`",
        f"Trivy high/critical findings: **{payload['trivy_high_critical_findings']}**",
        "",
        "## Dockerfile Policy Findings",
        "",
    ]
    for d in payload["dockerfiles"]:
        if not d["issues"]:
            lines.append(f"- `{d['dockerfile']}` -> PASS")
        else:
            lines.append(f"- `{d['dockerfile']}` -> FAIL ({', '.join(d['issues'])})")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
