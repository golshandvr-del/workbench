# Security policy

## Reporting
Please report vulnerabilities privately via **GitHub → Security → Report a vulnerability** on this repository. Do not open public issues for security problems.

## Handling of secrets in this project
- GitHub tokens used by the desktop app are stored in **Windows Credential Manager**, never in project files, URLs, logs or process arguments (redaction is unit-tested).
- Android release signing keys exist only as GitHub Actions secrets (`AIWB_KEYSTORE_*`, `AIWB_KEY_*`) and an offline owner backup. They are never committed (`.gitignore` blocks `*.p12`, `*.jks`, `*.keystore`).
- Release certificate SHA-256 (verify any APK against it):
  `6F:88:0A:C2:36:94:D0:C4:C0:E3:B5:9B:35:7D:F2:CE:A2:09:14:7B:7A:2E:01:7D:88:ED:2F:CE:87:3F:8D:59`
- Every release publishes SHA-256 sums; installers are byte-reproducible from the tag (`tools/build_desktop_installer.py`).

## Supported versions
Only the latest `desktop-v*` and `mobile-v*` releases receive fixes.
