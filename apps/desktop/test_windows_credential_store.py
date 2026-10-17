"""Native Windows integration test for the Credential Manager adapter.

Run on a Windows target machine: python test_windows_credential_store.py
Uses a synthetic test string, never a real GitHub token, and deletes the entry.
"""
from __future__ import annotations

import os
import sys
import uuid

from aiwb.github.credential_store import CredentialStoreError, WindowsCredentialStore


def main() -> int:
    if os.name != "nt":
        print("NOT RUN: Windows Credential Manager native test requires Windows.")
        return 2
    credential_ref = "github-api:" + str(uuid.uuid4())
    synthetic_secret = "AIWB-CREDENTIAL-STORE-NATIVE-TEST-" + str(uuid.uuid4())
    replacement_secret = synthetic_secret + "-REPLACED"
    store = WindowsCredentialStore()
    try:
        store.set_secret(credential_ref, synthetic_secret)
        assert store.get_secret(credential_ref) == synthetic_secret, "Credential Manager round-trip mismatch"
        store.set_secret(credential_ref, replacement_secret)
        assert store.get_secret(credential_ref) == replacement_secret, "Credential Manager replacement mismatch"
        store.delete_secret(credential_ref)
        try:
            store.get_secret(credential_ref)
        except CredentialStoreError:
            pass
        else:
            raise AssertionError("Credential remains readable after deletion")
        print("PASS: Windows Credential Manager set/read/replace/delete round-trip")
        return 0
    finally:
        try:
            store.delete_secret(credential_ref)
        except CredentialStoreError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
