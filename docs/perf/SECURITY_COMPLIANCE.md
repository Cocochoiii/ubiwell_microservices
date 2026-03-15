# Security and Compliance Controls

This document defines security/compliance controls added for enterprise readiness.

## Controls

- Dependency vulnerability scan (`scripts/dependency_vuln_scan.py`)
- Secret scan (`scripts/secret_scan.py`)
- Container scan (`scripts/container_scan.py`)
- SBOM generation (`scripts/generate_sbom.py`)
- Signed release checklist (`scripts/sign_release_checklist.py`)

## Runbook

```bash
make security-compliance
make security-verify-checklist
make release-gate-strict
```

## Artifacts

- `docs/perf/results/dependency-vuln-scan.json`
- `docs/perf/results/secret-scan.json`
- `docs/perf/results/container-scan.json`
- `docs/perf/results/sbom.cdx.json`
- `docs/perf/results/release-checklist-signature.json`

## Governance

- Release approval requires a passing strict release gate or documented risk waiver.
- Checklist signatures should use `RELEASE_SIGNING_KEY` in CI for tamper-evident sign-off.
