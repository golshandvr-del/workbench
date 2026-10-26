$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:PythonProbeLog = New-Object 'System.Collections.Generic.List[string]'
$script:PythonProbeCode = "import sys; print('AIWB_EXE=' + sys.executable); print('AIWB_VERSION=' + str(sys.version_info[0]) + '.' + str(sys.version_info[1])); import tkinter; tkinter.Tcl().eval('info patchlevel'); print('AIWB_TKINTER=OK')"

function Write-Step([string]$Message) {
    Write-Host "[AI Workbench] $Message" -ForegroundColor Cyan
}

function Invoke-CapturedProcess([string]$FilePath, [string]$Arguments, [int]$TimeoutSeconds = 15) {
    $process = $null
    try {
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $FilePath
        $startInfo.Arguments = $Arguments
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.CreateNoWindow = $true

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            return [PSCustomObject]@{ ExitCode = -1; StdOut = ''; StdErr = 'Process.Start returned false'; TimedOut = $false }
        }
        # Read both streams asynchronously, so neither redirected pipe can fill and block the process.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            try { $process.WaitForExit() } catch { }
            return [PSCustomObject]@{ ExitCode = -2; StdOut = ''; StdErr = "Timed out after $TimeoutSeconds seconds"; TimedOut = $true }
        }
        # WaitForExit() without a timeout flushes asynchronous process events on .NET Framework.
        $process.WaitForExit()
        return [PSCustomObject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdoutTask.Result
            StdErr = $stderrTask.Result
            TimedOut = $false
        }
    } catch {
        return [PSCustomObject]@{ ExitCode = -1; StdOut = ''; StdErr = $_.Exception.Message; TimedOut = $false }
    } finally {
        if ($process) { $process.Dispose() }
    }
}

function Get-ProbeMarker([string]$Text, [string]$Marker) {
    foreach ($line in ($Text -split "`r?`n")) {
        $trimmed = ([string]$line).Trim()
        if ($trimmed.StartsWith($Marker, [System.StringComparison]::Ordinal)) {
            return $trimmed.Substring($Marker.Length).Trim()
        }
    }
    return $null
}

function Test-PythonExe([string]$ExePath) {
    if ([string]::IsNullOrWhiteSpace($ExePath) -or -not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
        return $null
    }

    # Use ProcessStartInfo rather than PowerShell's native-command pipeline. This preserves
    # the complete -c argument on Windows PowerShell and captures stderr for diagnosis.
    $arguments = '-c "' + $script:PythonProbeCode + '"'
    $result = Invoke-CapturedProcess -FilePath $ExePath -Arguments $arguments -TimeoutSeconds 15
    $versionText = Get-ProbeMarker -Text $result.StdOut -Marker 'AIWB_VERSION='
    $tkText = Get-ProbeMarker -Text $result.StdOut -Marker 'AIWB_TKINTER='
    $reportedExe = Get-ProbeMarker -Text $result.StdOut -Marker 'AIWB_EXE='

    if ($result.ExitCode -ne 0 -or -not $versionText -or $tkText -ne 'OK') {
        $reason = if ($result.TimedOut) { 'probe timed out' } elseif ($result.ExitCode -ne 0) { "exit=$($result.ExitCode)" } elseif (-not $versionText) { 'version marker missing' } elseif ($tkText -ne 'OK') { 'Tkinter marker missing' } else { 'validation failed' }
        $detail = $result.StdErr
        if ([string]::IsNullOrWhiteSpace($detail)) { $detail = $result.StdOut }
        if ([string]::IsNullOrWhiteSpace($detail)) { $detail = '(no stdout/stderr)' }
        $script:PythonProbeLog.Add("FAIL: $ExePath | $reason | $detail")
        return $null
    }

    $versionParts = $versionText.Split('.')
    if ($versionParts.Count -lt 2) {
        $script:PythonProbeLog.Add("FAIL: $ExePath | malformed version marker: $versionText")
        return $null
    }
    try {
        $major = [int]$versionParts[0]
        $minor = [int]$versionParts[1]
    } catch {
        $script:PythonProbeLog.Add("FAIL: $ExePath | invalid version marker: $versionText")
        return $null
    }
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        $script:PythonProbeLog.Add("FAIL: $ExePath | Python $versionText is older than 3.10")
        return $null
    }

    $resolvedExe = $ExePath
    if ($reportedExe -and (Test-Path -LiteralPath $reportedExe -PathType Leaf)) { $resolvedExe = $reportedExe }
    $script:PythonProbeLog.Add("PASS: $resolvedExe | Python $versionText | Tcl/Tk available")
    return [PSCustomObject]@{ ExePath = $resolvedExe; Version = "$major.$minor" }
}

function Find-Python {
    # Refresh PATH from the registry: winget may have updated it after this
    # installer process started, and child processes inherit the old PATH.
    try {
        $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        $combinedPath = @($machinePath, $userPath, $env:Path) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
        $env:Path = ($combinedPath -join ';')
    } catch { }

    $launcherPaths = @()
    foreach ($commandName in @('py.exe', 'pymanager.exe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source) { $launcherPaths += $command.Source }
    }
    if ($env:LOCALAPPDATA) {
        $launcherPaths += (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe')
        $launcherPaths += (Join-Path $env:LOCALAPPDATA 'Programs\Python\PythonCore\py.exe')
    }
    if ($env:WINDIR) { $launcherPaths += (Join-Path $env:WINDIR 'py.exe') }

    foreach ($launcher in @($launcherPaths | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { continue }
        foreach ($tag in @('-3.14', '-3.13', '-3.12', '-3.11', '-3.10', '-3')) {
            $arguments = $tag + ' -c "' + $script:PythonProbeCode + '"'
            $launchResult = Invoke-CapturedProcess -FilePath $launcher -Arguments $arguments -TimeoutSeconds 20
            if ($launchResult.ExitCode -eq 0) {
                $candidate = Get-ProbeMarker -Text $launchResult.StdOut -Marker 'AIWB_EXE='
                if ($candidate) {
                    $tested = Test-PythonExe $candidate
                    if ($tested) { return $tested }
                }
            }
        }
    }

    $candidatePaths = New-Object 'System.Collections.Generic.List[string]'
    $knownFiles = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.13-64\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.12-64\python.exe')
    )
    foreach ($knownFile in $knownFiles) { if ($knownFile) { $candidatePaths.Add($knownFile) } }

    # Search standard per-user and per-machine locations. Limit recursion to one install root
    # level to avoid walking unrelated folders and virtual environments.
    $roots = @()
    if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA 'Programs\Python') }
    if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA 'Python') }
    if ($env:ProgramFiles) { $roots += $env:ProgramFiles }
    if (${env:ProgramFiles(x86)}) { $roots += ${env:ProgramFiles(x86)} }
    foreach ($root in @($roots | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        try {
            Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^(Python\d+|pythoncore-\d+\.\d+|Python\d+\.\d+)' } |
                Sort-Object Name -Descending |
                ForEach-Object { $candidatePaths.Add((Join-Path $_.FullName 'python.exe')) }
        } catch { }
    }

    # Query CPython's registry records as another source of install paths.
    $registryRoots = @(
        'HKCU:\Software\Python\PythonCore',
        'HKLM:\Software\Python\PythonCore',
        'HKLM:\Software\WOW6432Node\Python\PythonCore'
    )
    foreach ($registryRoot in $registryRoots) {
        if (-not (Test-Path -LiteralPath $registryRoot)) { continue }
        try {
            foreach ($versionKey in (Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue)) {
                $installPathKey = Join-Path $versionKey.PSPath 'InstallPath'
                if (Test-Path -LiteralPath $installPathKey) {
                    $regItem = Get-Item -LiteralPath $installPathKey -ErrorAction SilentlyContinue
                    $installDir = $null
                    if ($regItem) { $installDir = $regItem.GetValue('') }
                    if (-not $installDir -and $regItem) { $installDir = $regItem.GetValue('ExecutablePath') }
                    if ($installDir) {
                        if (Test-Path -LiteralPath $installDir -PathType Leaf) { $candidatePaths.Add($installDir) }
                        else { $candidatePaths.Add((Join-Path $installDir 'python.exe')) }
                    }
                }
            }
        } catch { }
    }

    # PATH commands are tried last, because WindowsApps entries can be placeholders.
    foreach ($commandName in @('python.exe', 'python3.exe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source) { $candidatePaths.Add($command.Source) }
    }

    foreach ($candidatePath in @($candidatePaths | Select-Object -Unique)) {
        $tested = Test-PythonExe $candidatePath
        if ($tested) { return $tested }
    }
    return $null
}
try {
    Write-Step 'Checking Python 3.10+ and Tkinter...'
    $python = Find-Python
    if (-not $python) {
        $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw 'Python 3.10+ with Tkinter was not found, and winget is unavailable. Install Python from https://www.python.org/downloads/windows/ and run this installer again.'
        }
        $installed = $false
        foreach ($packageId in @('Python.Python.3.13', 'Python.Python.3.14', 'Python.Python.3.12')) {
            Write-Step "Trying to install/repair $packageId with Tcl/Tk enabled for the current user..."
            try {
                # Include_tcltk=1 is explicit; some existing installs may have omitted Tcl/Tk.
                # --force bypasses winget's 'already installed/no upgrade' short-circuit.
                $override = '/quiet /norestart InstallAllUsers=0 PrependPath=1 Include_exe=1 Include_lib=1 Include_pip=1 Include_launcher=1 Include_tcltk=1 Include_test=0'
                & $winget.Source install --id $packageId --exact --scope user --accept-package-agreements --accept-source-agreements --silent --force --override $override
                if ($LASTEXITCODE -eq 0) {
                    $installed = $true
                    break
                }
            } catch {
                $script:PythonProbeLog.Add("winget attempt failed for $packageId : $($_.Exception.Message)")
            }
        }
        if (-not $installed) {
            throw 'Python could not be installed automatically. Install Python 3.10+ with Tkinter, then run this installer again.'
        }
        # Give the installer a short window to finish registering paths and shortcuts.
        for ($attempt = 0; $attempt -lt 8 -and -not $python; $attempt++) {
            Start-Sleep -Seconds 2
            $python = Find-Python
        }
        if (-not $python) {
            $diagnostic = Join-Path $env:TEMP 'AIWorkbench-python-diagnostic.txt'
            $details = @()
            $details += 'Python was installed by winget, but no Python 3.10+ runtime with Tkinter passed validation.'
            $details += ('User: ' + $env:USERNAME)
            $details += ('LocalAppData: ' + $env:LOCALAPPDATA)
            $details += ('PATH: ' + $env:Path)
            $details += 'python.exe candidates found:'
            $diagnosticRoots = @()
            if ($env:LOCALAPPDATA) { $diagnosticRoots += (Join-Path $env:LOCALAPPDATA 'Programs\Python') }
            if ($env:LOCALAPPDATA) { $diagnosticRoots += (Join-Path $env:LOCALAPPDATA 'Python') }
            if ($env:ProgramFiles) { $diagnosticRoots += (Join-Path $env:ProgramFiles 'Python') }
            if (${env:ProgramFiles(x86)}) { $diagnosticRoots += (Join-Path ${env:ProgramFiles(x86)} 'Python') }
            foreach ($root in $diagnosticRoots) {
                if (Test-Path -LiteralPath $root -PathType Container) {
                    $found = Get-ChildItem -LiteralPath $root -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
                    if ($found) { $details += $found }
                }
            }
            $details += ''
            $details += 'Python validation attempts:'
            if ($script:PythonProbeLog.Count -gt 0) { $details += $script:PythonProbeLog.ToArray() }
            else { $details += '(no candidate probe results were recorded)' }
            $details += ''
            $details += 'Launcher discovery:'
            foreach ($name in @('py.exe', 'pymanager.exe', 'python.exe', 'python3.exe')) {
                $cmd = Get-Command $name -ErrorAction SilentlyContinue
                if ($cmd -and $cmd.Source) { $details += ($name + ' => ' + $cmd.Source) }
                else { $details += ($name + ' => not found on PATH') }
            }
            $utf8NoBom = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList @($false)
            [System.IO.File]::WriteAllLines($diagnostic, [string[]]$details, $utf8NoBom)
            throw ('Python was installed, but a usable runtime could not be detected. Diagnostic written to: ' + $diagnostic + '. Please open the file and send its contents.')
        }
    }
    Write-Step "Using Python $($python.Version): $($python.ExePath)"

    $payloadDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $installDir = Join-Path $env:LOCALAPPDATA 'Programs\AIWorkbench'
    $dataDir = Join-Path $env:LOCALAPPDATA 'AIWorkbench'
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $dataDir 'backups') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $dataDir 'logs') -Force | Out-Null
    # 5.13.0 (owner audit C1): Python trusts __pycache__ when the source keeps its size and mtime. The payload's files
    # all carry the same date and a version bump changes only a digit, so the previous version's bytecode stayed
    # "valid" and the old app kept running after an update. Drop every cached .pyc before copying the new sources.
    if (Test-Path -LiteralPath $installDir -PathType Container) {
        Get-ChildItem -LiteralPath $installDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
        Get-ChildItem -LiteralPath $installDir -Recurse -File -Filter '*.pyc' -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
    }

    foreach ($fileName in @('AI_Workbench.py', 'conversation_store.py', 'project_version_store.py', 'restore_service.py', 'validation_profiles.py', 'README.md', 'README_FA.md', 'ARCHITECTURE.md', 'CHANGELOG.md', 'test_workbench.py', 'test_conversation_history.py', 'test_project_version_store.py', 'test_restore_service.py', 'test_validation_profiles.py', 'test_v114_features.py', 'test_git_service.py', 'test_github_accounts.py', 'test_github_repository_browser.py', 'test_github_repository_binding_v144.py', 'test_windows_credential_store.py', 'test_git_sync.py', 'test_github_actions.py', 'WINDOWS_RELEASE_CHECKLIST_v5.12.0.md', 'test_github_artifacts.py', 'test_orchestrator.py', 'test_rc_hardening.py', 'test_inbox.py', 'test_intake_normalize.py', 'test_ui_actions.py', 'test_timeline_canvas.py', 'test_v2_charter.py', 'test_v2_guide.py', 'test_repair_diagnostics.py', 'test_context_request.py', 'test_v2_model.py', 'test_v2_flow.py', 'test_v2_reference_scenario.py', 'test_v2_controller.py', 'test_i18n.py', 'test_companion.py', 'test_qr_pairing.py', 'test_workspace.py', 'test_team_planner.py', 'test_workflow_timeline.py', 'test_dashboard.py', 'test_gui_design_system.py', 'test_single_shell.py', 'test_bundle.py', 'test_release_gate.py', 'test_verify_step.py', 'test_flow.py', 'test_waves.py', 'test_diagnose.py', 'test_files.py', 'test_report.py', 'test_repo.py', 'test_closeout.py', 'test_algorithm_e2e.py', 'test_visual5_foundation.py', 'test_ui_tree.py', 'launch_aiwb.py', 'test_shell5.py', 'test_mission_model.py', 'test_motion.py', 'test_task_menu.py', 'test_ui_map.py', 'test_ui_balance.py', 'test_agent_hub.py', 'test_agents_cards.py', 'test_projects_cards.py', 'test_shared_tokens.py', 'test_mission_fixture.py', 'test_ui_call_signatures.py', 'test_profile_to_charter.py', 'test_team_setup.py', 'test_answer_files.py', 'test_answer_preview.py', 'test_answer_corpus.py', 'test_next_card.py', 'test_copy_damage.py', 'test_context_forgiving.py', 'test_context_step.py')) {
        $source = Join-Path $payloadDir $fileName
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Installer payload is incomplete; missing $fileName"
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $installDir $fileName) -Force
    }

    # The v1.14 modular domain services are a required runtime package, not optional docs/tests.
    $aiwbSource = Join-Path $payloadDir 'aiwb'
    $aiwbDestination = Join-Path $installDir 'aiwb'
    if (-not (Test-Path -LiteralPath $aiwbSource -PathType Container)) {
        throw 'Installer payload is incomplete; missing aiwb module package'
    }
    New-Item -ItemType Directory -Path $aiwbDestination -Force | Out-Null
    foreach ($moduleName in @('__init__.py', 'architecture_plan.py', 'candidate_store.py', 'dependency_analysis.py', 'semantic_diff.py', 'task_playbooks.py', 'git/__init__.py', 'git/models.py', 'git/service.py', 'git/sync.py', 'git/review_dialog.py', 'github/__init__.py', 'github/actions.py', 'github/build_center.py', 'github/redaction.py', 'github/credential_store.py', 'github/api_client.py', 'github/accounts.py', 'github/repository_binding.py', 'github/artifacts.py', 'github/build_center_dialogs.py', 'github/orchestrator.py', 'github/sync_build_window.py', 'inbox/__init__.py', 'inbox/store.py', 'inbox/attempts.py', 'inbox/classify.py', 'inbox/errors.py', 'inbox/salvage.py', 'inbox/pipeline.py', 'inbox/inbox_window.py', 'inbox/repair.py', 'diagnostics.py', 'context_request.py', 'context_request_window.py', 'v2/__init__.py', 'v2/models.py', 'v2/store.py', 'v2/agents.py', 'v2/tasks.py', 'v2/attempts.py', 'v2/ledger.py', 'v2/handoff.py', 'v2/snapshot.py', 'v2/publisher.py', 'v2/proposals.py', 'v2/next_action.py', 'v2/controller.py', 'v2/projects_window.py', 'i18n.py', 'companion/__init__.py', 'companion/crypto.py', 'companion/pairing.py', 'companion/service.py', 'companion/server.py', 'companion/window.py', 'workspace/__init__.py', 'workspace/theme.py', 'workspace/controller.py', 'workspace/shell.py', 'v2/events.py', 'v2/resources.py', 'v2/team.py', 'v2/workflow.py', 'v2/timeline.py', 'v2/dashboard.py', 'v2/changes.py', 'v2/charter.py', 'v2/guide.py', 'ui/__init__.py', 'ui/appearance.py', 'ui/prefs.py', 'ui/shell.py', 'ui/layout.py', 'ui/actions.py', 'ui/timeline_canvas.py', 'ui/qr.py', 'intake/__init__.py', 'intake/normalize.py', 'ui/sv_theme/sv.tcl', 'ui/sv_theme/LICENSE', 'ui/sv_theme/README.txt', 'ui/sv_theme/theme/light.tcl', 'ui/sv_theme/theme/dark.tcl', 'ui/sv_theme/theme/sprites_light.tcl', 'ui/sv_theme/theme/sprites_dark.tcl', 'ui/sv_theme/theme/spritesheet_light.png', 'ui/sv_theme/theme/spritesheet_dark.png', 'v2/bundle.py', 'v2/flow.py', 'v2/waves.py', 'v2/diagnose.py', 'v2/files.py', 'v2/report.py', 'v2/repo.py', 'v2/closeout.py', 'ui/raster.py', 'ui/tokens5.py', 'ui/assets.py', 'ui/structure5.py', 'ui/startup.py', 'ui/chrome5.py', 'ui/status5.py', 'ui/mission_model.py', 'ui/mission_canvas.py', 'ui/motion.py', 'ui/task_menu.py', 'ui/menu5.py', 'ui/ui_map.py', 'ui/map_view.py', 'v2/agent_hub.py', 'ui/agents5.py', 'ui/projects5.py', 'v2/team_setup.py', 'ui/team_table.py', 'ui/project_wizard.py', 'intake/lenient.py', 'intake/answer_files.py', 'intake/preview.py', 'v2/charter_repair.py', 'ui/paste_box.py', 'ui/next_card.py', 'v2/context_step.py')) {
        $relativeModule = $moduleName.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $moduleSource = Join-Path $aiwbSource $relativeModule
        if (-not (Test-Path -LiteralPath $moduleSource -PathType Leaf)) {
            throw "Installer payload is incomplete; missing aiwb/$moduleName"
        }
        $moduleDestination = Join-Path $aiwbDestination $relativeModule
        $moduleDestinationDir = Split-Path -Parent $moduleDestination
        New-Item -ItemType Directory -Path $moduleDestinationDir -Force | Out-Null
        Copy-Item -LiteralPath $moduleSource -Destination $moduleDestination -Force
    }
    Copy-Item -LiteralPath (Join-Path $payloadDir 'uninstall.bat') -Destination (Join-Path $installDir 'uninstall.bat') -Force

    $pythonwPath = Join-Path (Split-Path -Parent $python.ExePath) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
        # A few installations expose only python.exe; in that case use a hidden WScript launch.
        $pythonwPath = $python.ExePath
    }
    # Roadmap 5.0.0: pre-compile once so every start loads cached bytecode, and start through the splash launcher.
    try { & $python.ExePath -m compileall -f -q -j 0 $installDir | Out-Null } catch { Write-Step 'Pre-compiling skipped (not required).' }
    $appScript = Join-Path $installDir 'launch_aiwb.py'
    if (-not (Test-Path -LiteralPath $appScript -PathType Leaf)) { $appScript = Join-Path $installDir 'AI_Workbench.py' }
    $vbsPath = Join-Path $installDir 'launch.vbs'
    $vbsPython = $pythonwPath.Replace('"', '""')
    $vbsScript = $appScript.Replace('"', '""')
    $vbs = @"
Set sh = CreateObject("WScript.Shell")
cmd = Chr(34) & "$vbsPython" & Chr(34) & " " & Chr(34) & "$vbsScript" & Chr(34)
sh.Run cmd, 0, False
"@
    $utf8NoBom = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList @($false)
    [System.IO.File]::WriteAllText($vbsPath, $vbs, $utf8NoBom)

    $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $desktopLink = Join-Path $desktop 'AI Workbench.lnk'
    $shortcut = $shell.CreateShortcut($desktopLink)
    $shortcut.TargetPath = $wscript
    $shortcut.Arguments = "`"$vbsPath`""
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Description = 'AI Workbench — local project command bridge'
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
    $shortcut.Save()

    $startMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    $startLink = Join-Path $startMenuDir 'AI Workbench.lnk'
    $startShortcut = $shell.CreateShortcut($startLink)
    $startShortcut.TargetPath = $wscript
    $startShortcut.Arguments = "`"$vbsPath`""
    $startShortcut.WorkingDirectory = $installDir
    $startShortcut.Description = 'AI Workbench — local project command bridge'
    $startShortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
    $startShortcut.Save()

    Write-Step 'Installation complete.'
    Write-Host "Program: $installDir" -ForegroundColor Green
    Write-Host "Settings and backups: $dataDir" -ForegroundColor Green
    Write-Host 'A desktop shortcut was created. Launching the application now...' -ForegroundColor Green
    Start-Process -FilePath $wscript -ArgumentList @("`"$vbsPath`"")
    exit 0
} catch {
    Write-Host ''
    Write-Host "INSTALLATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No project files were modified by the installer.' -ForegroundColor Yellow
    exit 1
}
