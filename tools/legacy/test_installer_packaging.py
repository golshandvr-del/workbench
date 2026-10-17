#!/usr/bin/env python3
"""String/byte-level regression test for the self-extracting Windows installer."""
from __future__ import annotations

import base64
import re
import sys
import io
import zipfile
from pathlib import Path

BEGIN = "###AIWB_PAYLOAD_BEGIN###"
END = "###AIWB_PAYLOAD_END###"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python test_installer_packaging.py <installer.bat> <payload.zip>", file=sys.stderr)
        return 2
    installer_path, payload_path = map(Path, sys.argv[1:])
    raw = installer_path.read_bytes()
    text = raw.decode("ascii")
    lines = text.splitlines()
    assert lines[0] == "@echo off", "not a batch installer"
    assert "-EncodedCommand " in lines[3], "bootstrap must use one-line EncodedCommand"
    command = lines[3].split("-EncodedCommand ", 1)[1].strip()
    bootstrap = base64.b64decode(command).decode("utf-16le")
    assert "FromBase64String" in bootstrap
    assert "ReadAllLines($self)" in bootstrap
    assert "-ceq '###AIWB_PAYLOAD_BEGIN###'" in bootstrap
    assert "-ceq '###AIWB_PAYLOAD_END###'" in bootstrap
    assert "###AIWB_PAYLOAD_BEGIN###" in lines and "###AIWB_PAYLOAD_END###" in lines
    begin = lines.index(BEGIN)
    end = lines.index(END)
    assert begin > 0 and end > begin + 1
    assert lines.index("exit /b %_AIWB_EXIT%") < begin, "payload must be after the batch exit"
    payload_b64 = "".join(line.strip() for line in lines[begin + 1 : end])
    embedded = base64.b64decode(payload_b64, validate=True)
    expected = payload_path.read_bytes()
    assert embedded == expected, "embedded bytes differ from the source ZIP"
    assert embedded.startswith(b"PK\x03\x04"), "embedded payload isn't ZIP data"
    with zipfile.ZipFile(io.BytesIO(embedded)) as archive:
        names = set(archive.namelist())
        required = {
            "install.ps1", "AI_Workbench.py", "conversation_store.py", "project_version_store.py",
            "restore_service.py", "validation_profiles.py", "README.md", "README_FA.md", "test_workbench.py", "test_conversation_history.py",
            "test_project_version_store.py", "test_restore_service.py", "test_validation_profiles.py", "test_v114_features.py", "ARCHITECTURE.md", "CHANGELOG.md", "uninstall.bat",
            "aiwb/__init__.py", "aiwb/architecture_plan.py", "aiwb/candidate_store.py", "aiwb/dependency_analysis.py", "aiwb/semantic_diff.py", "aiwb/task_playbooks.py",
            "aiwb/git/__init__.py", "aiwb/git/models.py", "aiwb/git/service.py", "test_git_service.py",
            "aiwb/github/__init__.py", "aiwb/github/redaction.py", "aiwb/github/credential_store.py", "aiwb/github/api_client.py", "aiwb/github/accounts.py", "aiwb/github/repository_binding.py",
            "test_github_accounts.py", "test_github_repository_browser.py", "test_github_repository_binding_v144.py", "test_windows_credential_store.py",
        }
        # Monorepo adaptation: the release checklist name follows the release version.
        checklists = sorted(n for n in names if re.fullmatch(r"WINDOWS_RELEASE_CHECKLIST_v\d+\.\d+\.\d+\.md", n))
        assert checklists, "installer payload has no WINDOWS_RELEASE_CHECKLIST_v*.md"
        required.add(checklists[-1])
        missing = sorted(required - names)
        assert not missing, f"installer payload missing release files: {missing}"
        installer_script = archive.read("install.ps1").decode("utf-8-sig")
        for name in sorted(required - {"install.ps1", "uninstall.bat"}):
            script_name = name.split("/", 1)[1] if name.startswith("aiwb/") else name
            assert f"'{script_name}'" in installer_script, f"install.ps1 does not copy required file {name}"
        for module in ("__init__.py", "architecture_plan.py", "candidate_store.py", "dependency_analysis.py", "semantic_diff.py", "task_playbooks.py", "git/__init__.py", "git/models.py", "git/service.py", "github/__init__.py", "github/redaction.py", "github/credential_store.py", "github/api_client.py", "github/accounts.py", "github/repository_binding.py"):
            assert module in installer_script, f"install.ps1 does not install module {module}"
    # The multiline payload must not be part of the `powershell.exe` command line.
    assert len(lines[3]) < 8000, "command line exceeds conservative Windows limit"
    print(f"PASS: installer wrapper, markers, encoded bootstrap and payload identity ({len(embedded):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
