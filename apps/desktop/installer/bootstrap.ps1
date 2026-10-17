$ErrorActionPreference = 'Stop'
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
}