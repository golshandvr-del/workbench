"""Operating-system credential storage for GitHub REST API tokens.

Production Windows builds use Windows Credential Manager via Advapi32. Tokens are
never written to Workbench settings, project files, Git remotes, or command-line args.
"""
from __future__ import annotations

import ctypes
import os
import threading
import uuid
from ctypes import wintypes
from typing import Protocol


class CredentialStoreError(RuntimeError):
    """Credential storage failed; message is safe for UI display."""


class UnsupportedCredentialStore(CredentialStoreError):
    pass


class CredentialStore(Protocol):
    def set_secret(self, credential_ref: str, secret: str) -> None: ...
    def get_secret(self, credential_ref: str) -> str: ...
    def delete_secret(self, credential_ref: str) -> None: ...


def _validate_ref(credential_ref: str) -> str:
    if not isinstance(credential_ref, str) or not credential_ref.startswith("github-api:"):
        raise CredentialStoreError("Invalid credential reference.")
    suffix = credential_ref.partition(":")[2]
    try:
        parsed = uuid.UUID(suffix)
    except (ValueError, AttributeError) as exc:
        raise CredentialStoreError("Invalid credential reference.") from exc
    if str(parsed) != suffix:
        raise CredentialStoreError("Invalid credential reference.")
    return "AIWorkbench/GitHub/API/" + str(parsed)


class MemoryCredentialStore:
    """Non-persistent test double. Never selected by the production factory."""
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = threading.RLock()

    def set_secret(self, credential_ref: str, secret: str) -> None:
        target = _validate_ref(credential_ref)
        if not isinstance(secret, str) or not secret:
            raise CredentialStoreError("Credential secret is empty.")
        with self._lock:
            self._values[target] = secret

    def get_secret(self, credential_ref: str) -> str:
        target = _validate_ref(credential_ref)
        with self._lock:
            try:
                return self._values[target]
            except KeyError as exc:
                raise CredentialStoreError("The saved GitHub credential is missing. Replace the credential to reconnect.") from exc

    def delete_secret(self, credential_ref: str) -> None:
        target = _validate_ref(credential_ref)
        with self._lock:
            self._values.pop(target, None)


class WindowsCredentialStore:
    """Windows Credential Manager adapter for generic persistent credentials."""
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    class _CREDENTIALW(ctypes.Structure):
        pass

    _CREDENTIALW._fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]

    def __init__(self) -> None:
        if os.name != "nt":
            raise UnsupportedCredentialStore("GitHub PAT storage requires Windows Credential Manager on this platform.")
        try:
            self._advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)  # type: ignore[attr-defined]
            self._advapi.CredWriteW.argtypes = [ctypes.POINTER(self._CREDENTIALW), ctypes.c_uint32]
            self._advapi.CredWriteW.restype = wintypes.BOOL
            self._advapi.CredReadW.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(self._CREDENTIALW))]
            self._advapi.CredReadW.restype = wintypes.BOOL
            self._advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_uint32]
            self._advapi.CredDeleteW.restype = wintypes.BOOL
            self._advapi.CredFree.argtypes = [ctypes.c_void_p]
            self._advapi.CredFree.restype = None
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be initialized.") from exc

    @staticmethod
    def _target(credential_ref: str) -> str:
        return _validate_ref(credential_ref)

    @staticmethod
    def _raise_last_error(action: str, *, allow_not_found: bool = False) -> None:
        code = ctypes.get_last_error()
        if allow_not_found and code == 1168:  # ERROR_NOT_FOUND
            return
        # Do not include API buffers, token strings, or raw OS messages.
        raise CredentialStoreError(f"Windows Credential Manager could not {action} the GitHub credential (error {code}).")

    def set_secret(self, credential_ref: str, secret: str) -> None:
        target = self._target(credential_ref)
        if not isinstance(secret, str) or not secret or "\x00" in secret:
            raise CredentialStoreError("Credential secret is empty or invalid.")
        blob = secret.encode("utf-16-le")
        if len(blob) > 2560:
            raise CredentialStoreError("The credential exceeds the Windows Credential Manager size limit.")
        blob_buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self._CREDENTIALW()
        credential.Flags = 0
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.Comment = "AI Workbench GitHub REST API credential"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = "AI Workbench GitHub API"
        ctypes.set_last_error(0)
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            self._raise_last_error("save")

    def get_secret(self, credential_ref: str) -> str:
        target = self._target(credential_ref)
        pointer = ctypes.POINTER(self._CREDENTIALW)()
        ctypes.set_last_error(0)
        if not self._advapi.CredReadW(target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            code = ctypes.get_last_error()
            if code == 1168:
                raise CredentialStoreError("The saved GitHub credential is missing. Replace the credential to reconnect.")
            self._raise_last_error("read")
        try:
            credential = pointer.contents
            size = int(credential.CredentialBlobSize)
            if size <= 0 or size > 2560 or size % 2 != 0 or not credential.CredentialBlob:
                raise CredentialStoreError("The saved GitHub credential has an invalid format. Replace it to reconnect.")
            raw = ctypes.string_at(credential.CredentialBlob, size)
            try:
                secret = raw.decode("utf-16-le")
            except UnicodeDecodeError as exc:
                raise CredentialStoreError("The saved GitHub credential could not be decoded. Replace it to reconnect.") from exc
            if not secret:
                raise CredentialStoreError("The saved GitHub credential is empty. Replace it to reconnect.")
            return secret
        finally:
            self._advapi.CredFree(pointer)

    def delete_secret(self, credential_ref: str) -> None:
        target = self._target(credential_ref)
        ctypes.set_last_error(0)
        if not self._advapi.CredDeleteW(target, self.CRED_TYPE_GENERIC, 0):
            code = ctypes.get_last_error()
            if code == 1168:
                return
            self._raise_last_error("delete")


def create_default_credential_store() -> CredentialStore:
    """Return the production store; no plaintext or file-based fallback is allowed."""
    if os.name != "nt":
        return _UnsupportedStore()
    return WindowsCredentialStore()


class _UnsupportedStore:
    def _fail(self) -> None:
        raise UnsupportedCredentialStore("Secure GitHub PAT storage is currently supported only on Windows Credential Manager.")

    def set_secret(self, credential_ref: str, secret: str) -> None:
        self._fail()

    def get_secret(self, credential_ref: str) -> str:
        self._fail()

    def delete_secret(self, credential_ref: str) -> None:
        self._fail()
