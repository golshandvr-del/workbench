# Shared contracts

JSON Schemas (draft 2020-12) for data that **both** the desktop and the mobile app read.
Validated in CI by `tools/validate_contracts.py` (job `contracts`): every schema must be valid,
every `fixtures/valid/<schema>*.json` must validate and every `fixtures/invalid/<schema>*.json` must fail.

| Schema | Producer | Consumers |
|---|---|---|
| `release-manifest.v1` | `tools/build_desktop_installer.py`, `release-*.yml` | desktop release checks, mobile release browser |
| `build-metadata.v1` | CI / Sync & Build records | desktop Build Center, mobile (read-only) |
| `capabilities.v1` | `capabilities.yml` (repo root) | roadmap/status reporting only — **no feature gating** |

Policy: ADR-005.
