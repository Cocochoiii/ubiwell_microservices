#!/usr/bin/env python3
"""Generate a lightweight CycloneDX-like SBOM from manifests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
SBOM_PATH = RESULTS_DIR / "sbom.cdx.json"
SBOM_REPORT = ROOT / "docs" / "perf" / "SBOM_REPORT.md"


def parse_requirements(path: Path) -> list[dict]:
    components = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if "==" in text:
            name, version = text.split("==", 1)
        else:
            name, version = text, "unknown"
        components.append(
            {
                "type": "library",
                "name": name.strip(),
                "version": version.strip(),
                "purl": f"pkg:pypi/{name.strip()}@{version.strip()}",
            }
        )
    return components


def parse_package_json(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    components = []
    for section in ("dependencies", "devDependencies"):
        for name, version in (payload.get(section, {}) or {}).items():
            components.append(
                {
                    "type": "library",
                    "name": name,
                    "version": str(version),
                    "scope": section,
                    "purl": f"pkg:npm/{name}@{version}",
                }
            )
    return components


def main() -> int:
    components: list[dict] = []
    for req in sorted((ROOT / "services").glob("*/requirements.txt")):
        for c in parse_requirements(req):
            c["evidence"] = str(req.relative_to(ROOT))
            components.append(c)

    for pkg in sorted(ROOT.glob("apps/**/package.json")):
        for c in parse_package_json(pkg):
            c["evidence"] = str(pkg.relative_to(ROOT))
            components.append(c)

    for pkg in sorted(ROOT.glob("tools/**/package.json")):
        for c in parse_package_json(pkg):
            c["evidence"] = str(pkg.relative_to(ROOT))
            components.append(c)

    seen = set()
    deduped = []
    for c in components:
        key = (c["name"], c.get("version"), c.get("evidence"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:ubiwell-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {"type": "application", "name": "ubiwell_microservices"},
        },
        "components": deduped,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SBOM_PATH.write_text(json.dumps(sbom, indent=2), encoding="utf-8")

    report = "\n".join(
        [
            "# SBOM Report",
            "",
            f"Generated at: `{sbom['metadata']['timestamp']}`",
            f"Total components: **{len(deduped)}**",
            f"SBOM file: `{SBOM_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Notes",
            "",
            "- Format: CycloneDX-like JSON generated from repository manifests.",
            "- Includes Python and Node application dependencies in this monorepo.",
        ]
    )
    SBOM_REPORT.write_text(report, encoding="utf-8")
    print(f"Wrote {SBOM_PATH}")
    print(f"Wrote {SBOM_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
