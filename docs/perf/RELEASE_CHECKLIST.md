# Release Checklist

Use this checklist before production/demo release. Mark every item and then sign.

## Build and Test

- [ ] Backend tests pass (`make test-backend-coverage`)
- [ ] Frontend tests pass (`make test-frontend-jest`)
- [ ] iOS edge reliability benchmark generated (`make bench-ios-edge-reliability`)

## Reliability and Performance

- [ ] SLO report generated and reviewed (`make slo-report`)
- [ ] Release gate passes (`make release-gate`)
- [ ] Strict release gate passes (`make release-gate-strict`) or waiver documented

## Security and Compliance

- [ ] Dependency vulnerability scan generated (`make security-deps`)
- [ ] Secret scan generated (`make security-secrets`)
- [ ] Container scan generated (`make security-containers`)
- [ ] SBOM generated (`make security-sbom`)

## Sign-Off

- Owner:
- Team:
- Date (UTC):
- Risk waivers (if any):
