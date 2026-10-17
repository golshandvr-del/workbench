#!/usr/bin/env python3
"""Build a Windows self-extracting AI Workbench installer from a ZIP payload.

The wrapper deliberately keeps the Base64 payload outside the command line sent to
cmd.exe/PowerShell. The PowerShell bootstrap is UTF-16LE Base64 on one line, while
payload bytes are treated only as data between explicit marker lines.
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path

BEGIN_MARKER = "###AIWB_PAYLOAD_BEGIN###"
END_MARKER = "###AIWB_PAYLOAD_END###"

BOOTSTRAP = r'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$tempRoot = $null
try {
    $self = $env:_AIWB_SELF
    if ([string]::IsNullOrWhiteSpace($self) -or -not (Test-Path -LiteralPath $self -PathType Leaf)) {
        throw 'Installer path is unavailable.'
    }
    $lines = [System.IO.File]::ReadAllLines($self)
    $begin = -1
    $end = -1
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -ceq '###AIWB_PAYLOAD_BEGIN###') { $begin = $i }
        if ($lines[$i] -ceq '###AIWB_PAYLOAD_END###') { $end = $i; break }
    }
    if ($begin -lt 0 -or $end -le ($begin + 1)) {
        throw 'Embedded payload markers are missing, reversed, or empty.'
    }
    $payloadLines = New-Object 'System.Collections.Generic.List[string]'
    for ($i = $begin + 1; $i -lt $end; $i++) {
        $line = $lines[$i].Trim()
        if ($line.Length -gt 0) { $payloadLines.Add($line) }
    }
    $base64 = [string]::Join('', $payloadLines.ToArray())
    if ([string]::IsNullOrWhiteSpace($base64)) { throw 'Embedded payload is empty.' }
    $bytes = [System.Convert]::FromBase64String($base64)
    if ($bytes.Length -lt 4 -or $bytes[0] -ne 0x50 -or $bytes[1] -ne 0x4B) {
        throw 'Decoded payload is not a ZIP archive.'
    }
    $tempRoot = Join-Path $env:TEMP ('AIWorkbench-Setup-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $zipPath = Join-Path $tempRoot 'payload.zip'
    [System.IO.File]::WriteAllBytes($zipPath, $bytes)
    Expand-Archive -LiteralPath $zipPath -DestinationPath $tempRoot -Force
    $installScript = Join-Path $tempRoot 'install.ps1'
    if (-not (Test-Path -LiteralPath $installScript -PathType Leaf)) {
        throw 'Installer payload is incomplete; install.ps1 is missing.'
    }
    $powershellExe = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $powershellExe -PathType Leaf)) { $powershellExe = 'powershell.exe' }
    & $powershellExe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $installScript
    $installExitCode = $LASTEXITCODE
    if ($installExitCode -ne 0) { throw "The installation process exited with code $installExitCode." }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
} catch {
    Write-Host ''
    Write-Host ('AI Workbench installer failed: ' + $_.Exception.Message) -ForegroundColor Red
    if ($tempRoot -and (Test-Path -LiteralPath $tempRoot -PathType Container)) {
        Write-Host ('Temporary diagnostic files were retained at: ' + $tempRoot) -ForegroundColor Yellow
    }
    exit 1
}'''


def build_installer(payload: bytes) -> bytes:
    encoded_command = base64.b64encode(BOOTSTRAP.encode("utf-16le")).decode("ascii")
    if len(encoded_command) > 8000:
        raise ValueError("PowerShell bootstrap is too long for a safe Windows command line")
    payload_b64 = base64.b64encode(payload).decode("ascii")
    payload_lines = [payload_b64[i : i + 100] for i in range(0, len(payload_b64), 100)]
    header = [
        "@echo off",
        "setlocal DisableDelayedExpansion",
        'set "_AIWB_SELF=%~f0"',
        "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand " + encoded_command,
        'set "_AIWB_EXIT=%ERRORLEVEL%"',
        'if not "%_AIWB_EXIT%"=="0" (',
        "  echo.",
        "  echo AI Workbench installation failed. See the error above.",
        "  pause",
        ")",
        "exit /b %_AIWB_EXIT%",
        BEGIN_MARKER,
    ]
    lines = header + payload_lines + [END_MARKER, ""]
    return "\r\n".join(lines).encode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path, help="ZIP archive to embed")
    parser.add_argument("--output", required=True, type=Path, help="Destination .bat path")
    args = parser.parse_args()
    payload = args.payload.read_bytes()
    if not payload.startswith(b"PK\x03\x04"):
        parser.error("payload does not appear to be a ZIP archive")
    installer = build_installer(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(installer)
    print(f"Wrote {args.output} ({len(installer):,} bytes); embedded ZIP: {len(payload):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
