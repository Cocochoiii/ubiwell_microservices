#!/usr/bin/env python3
"""Lightweight secret scanner with regex rules and entropy checks."""

from __future__ import annotations

import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
REPORT_JSON = RESULTS_DIR / "secret-scan.json"
REPORT_MD = ROOT / "docs" / "perf" / "SECRET_SCAN_REPORT.md"

TEXT_FILE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".env",
    ".md",
    ".sh",
    ".txt",
    ".swift",
    ".sql",
    ".proto",
    ".toml",
    ".ini",
}
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".venv_test",
    ".venv_codegen",
    "node_modules",
    ".cursor",
    "dist",
    "build",
}
ALLOWLIST_PATH_SNIPPETS = {
    "docs/perf/screenshots/",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    "package-lock.json",
    ".coverage",
    "docs/perf/results/",
}

PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_pat": re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "private_key_block": re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----"),
    "generic_api_key_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9_\-\/+=]{12,}['\"]"
    ),
}


def shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    prob = [float(text.count(c)) / len(text) for c in set(text)]
    return -sum(p * math.log2(p) for p in prob)


def candidate_high_entropy_tokens(line: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9+/=_-]{24,}", line)
    filtered = []
    for token in tokens:
        if token.startswith("sha512-") or token.startswith("http") or "/" in token:
            continue
        if not (re.search(r"[A-Za-z]", token) and re.search(r"[0-9]", token)):
            continue
        if shannon_entropy(token) >= 4.0:
            filtered.append(token)
    return filtered


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(snippet in rel for snippet in ALLOWLIST_PATH_SNIPPETS):
        return True
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return True
    if path.suffix and path.suffix.lower() not in TEXT_FILE_SUFFIXES:
        return True
    return False


def main() -> int:
    findings: list[dict] = []
    tracked_files: list[Path] = []
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_files = [ROOT / p for p in proc.stdout.splitlines() if p.strip()]
    except Exception:
        tracked_files = [p for p in ROOT.rglob("*") if p.is_file()]

    for path in tracked_files:
        if should_skip(path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for idx, line in enumerate(content.splitlines(), start=1):
            for rule, regex in PATTERNS.items():
                match = regex.search(line)
                if match:
                    findings.append(
                        {
                            "file": rel,
                            "line": idx,
                            "rule": rule,
                            "match_preview": match.group(0)[:80],
                        }
                    )
            for token in candidate_high_entropy_tokens(line):
                findings.append(
                    {
                        "file": rel,
                        "line": idx,
                        "rule": "high_entropy_token",
                        "match_preview": token[:30] + "...",
                    }
                )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_findings": len(findings),
        "findings": findings[:500],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Secret Scan Report",
        "",
        f"Generated at: `{payload['generated_at']}`",
        f"Total findings: **{payload['total_findings']}**",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No potential secrets found by regex/entropy checks.")
    else:
        for f in findings[:200]:
            lines.append(
                f"- `{f['rule']}` in `{f['file']}` line `{f['line']}` (preview: `{f['match_preview']}`)"
            )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
