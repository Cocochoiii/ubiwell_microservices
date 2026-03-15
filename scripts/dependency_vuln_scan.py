#!/usr/bin/env python3
"""Dependency vulnerability scan for Python and Node manifests."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
REPORT_JSON = RESULTS_DIR / "dependency-vuln-scan.json"
REPORT_MD = ROOT / "docs" / "perf" / "DEPENDENCY_VULN_REPORT.md"


def run(cmd: list[str], cwd: Path | None = None, timeout_seconds: int = 90) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_seconds)
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, output.strip()
    except subprocess.TimeoutExpired:
        return 124, f"Command timed out after {timeout_seconds}s: {' '.join(cmd)}"


def parse_json_output(raw: str) -> dict | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def python_scan() -> dict:
    req_files = sorted((ROOT / "services").glob("*/requirements.txt"))
    if not req_files:
        return {"status": "skipped", "reason": "No Python requirements found", "vulnerabilities": []}

    if shutil.which("pip-audit") is None:
        return {
            "status": "tool_missing",
            "reason": "pip-audit not installed. Install with: pip install pip-audit",
            "vulnerabilities": [],
        }

    findings: list[dict] = []
    for req in req_files:
        code, out = run(["pip-audit", "-r", str(req), "--format", "json"])
        if not out:
            continue
        try:
            payload = parse_json_output(out)
            if payload is None:
                raise json.JSONDecodeError("Invalid JSON payload", out, 0)
            for dep in payload.get("dependencies", []):
                for vuln in dep.get("vulns", []):
                    findings.append(
                        {
                            "ecosystem": "python",
                            "manifest": str(req.relative_to(ROOT)),
                            "package": dep.get("name"),
                            "version": dep.get("version"),
                            "id": vuln.get("id"),
                            "fix_versions": vuln.get("fix_versions", []),
                            "description": vuln.get("description", ""),
                        }
                    )
        except json.JSONDecodeError:
            findings.append(
                {
                    "ecosystem": "python",
                    "manifest": str(req.relative_to(ROOT)),
                    "package": None,
                    "version": None,
                    "id": "SCAN_ERROR",
                    "fix_versions": [],
                    "description": out[:500],
                }
            )
        if code not in (0, 1):
            findings.append(
                {
                    "ecosystem": "python",
                    "manifest": str(req.relative_to(ROOT)),
                    "package": None,
                    "version": None,
                    "id": "TOOL_ERROR",
                    "fix_versions": [],
                    "description": out[:500],
                }
            )
    return {"status": "ok", "vulnerabilities": findings}


def node_scan() -> dict:
    dashboard_dir = ROOT / "apps" / "web-dashboard"
    if not (dashboard_dir / "package.json").exists():
        return {"status": "skipped", "reason": "No Node project found", "vulnerabilities": []}
    code, out = run(["npm", "audit", "--json"], cwd=dashboard_dir)
    if not out:
        return {"status": "ok", "vulnerabilities": []}
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return {
            "status": "scan_error",
            "reason": out[:500],
            "vulnerabilities": [],
        }

    findings: list[dict] = []
    vulnerabilities = payload.get("vulnerabilities", {})
    for package_name, meta in vulnerabilities.items():
        findings.append(
            {
                "ecosystem": "node",
                "manifest": "apps/web-dashboard/package.json",
                "package": package_name,
                "severity": meta.get("severity"),
                "range": meta.get("range"),
                "fix_available": meta.get("fixAvailable"),
            }
        )
    return {
        "status": "ok" if code in (0, 1) else "scan_error",
        "vulnerabilities": findings,
    }


def main() -> int:
    py = python_scan()
    node = node_scan()
    findings = py.get("vulnerabilities", []) + node.get("vulnerabilities", [])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_status": py.get("status"),
        "node_status": node.get("status"),
        "total_vulnerabilities": len(findings),
        "findings": findings,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Dependency Vulnerability Report",
        "",
        f"Generated at: `{payload['generated_at']}`",
        f"Python scan status: `{payload['python_status']}`",
        f"Node scan status: `{payload['node_status']}`",
        f"Total findings: **{payload['total_vulnerabilities']}**",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No vulnerabilities reported by current scanners.")
    else:
        for f in findings[:200]:
            lines.append(
                f"- `{f.get('ecosystem')}` `{f.get('package')}` "
                f"(manifest: `{f.get('manifest')}`) -> {f.get('id', f.get('severity', 'issue'))}"
            )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
