param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$NoBrowser,
    [ValidateRange(2, 60)][int]$StartupWaitSeconds = 25,
    [string]$AppRoot = ''
)

$ErrorActionPreference = 'Stop'

function Read-IrgsHealthJson([string]$Url) {
    $response = $null
    $reader = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = 'GET'
        $request.Proxy = $null
        $request.Timeout = 1200
        $request.ReadWriteTimeout = 1200
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        return ($reader.ReadToEnd() | ConvertFrom-Json)
    } catch {
        return $null
    } finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $response) { $response.Dispose() }
    }
}

function Get-IrgsHostState([int]$HostPort) {
    $baseUrl = "http://127.0.0.1:$HostPort"
    $catalogue = Read-IrgsHealthJson "$baseUrl/api/catalog"
    if ($null -ne $catalogue -and $catalogue.core.id -eq 'IRGS-CORE-3.3' -and
        [string]$catalogue.core.version -eq '3.3' -and $catalogue.core.single_world_per_campaign -eq $true) {
        $session = Read-IrgsHealthJson "$baseUrl/api/campaigns"
        if ($null -ne $session -and $session.PSObject.Properties.Name -contains 'campaigns' -and
            $session.token -is [string] -and $session.token.Length -ge 16) {
            return 'Ready'
        }
    }
    $connection = New-Object System.Net.Sockets.TcpClient
    $pending = $null
    try {
        $pending = $connection.BeginConnect('127.0.0.1', $HostPort, $null, $null)
        if ($pending.AsyncWaitHandle.WaitOne(300)) {
            $connection.EndConnect($pending)
            return 'Occupied'
        }
    } catch {
        # An absent listener is the only condition that permits a new host.
    } finally {
        if ($null -ne $pending) { $pending.AsyncWaitHandle.Close() }
        $connection.Close()
    }
    return 'Stopped'
}

function Confirm-IrgsRelease([string]$PythonPath, [string]$SuiteFolder) {
    $verification = & $PythonPath -B (Join-Path $SuiteFolder 'runtime\irgs.py') verify 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "IRGS could not verify its installed files. No new host was started. Restore the complete release package and try again.`n$($verification -join [Environment]::NewLine)"
    }
}

function Test-IrgsPython([string]$Command, [string[]]$Prefix) {
    # Returns the interpreter path only when it actually runs and is Python 3.12+.
    # The Microsoft Store "python" alias and older installations fail this probe.
    try {
        $probe = & $Command @Prefix -c 'import sys; print(sys.version_info[:2] >= (3, 12)); print(sys.executable)' 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) { return $null }
    $lines = @($probe)
    if ($lines.Count -lt 2 -or ([string]$lines[0]).Trim() -ne 'True') { return $null }
    $path = ([string]$lines[1]).Trim()
    if (-not $path -or -not (Test-Path -LiteralPath $path)) { return $null }
    return $path
}

function Resolve-IrgsPython {
    $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled) { return $bundled }
    $candidates = @(
        @{Command = 'python'; Prefix = @()},
        @{Command = 'python3'; Prefix = @()},
        @{Command = 'py'; Prefix = @('-3')}
    )
    foreach ($candidate in $candidates) {
        $found = Get-Command $candidate.Command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { continue }
        $path = Test-IrgsPython $found.Source $candidate.Prefix
        if ($path) { return $path }
    }
    throw ("IRGS needs Python 3.12 or newer, and none was found. No host was started.`n" +
        "Install Python from https://www.python.org/downloads/ and tick 'Add python.exe to PATH', " +
        "then run Start-IRGS.cmd again. The Microsoft Store 'python' shortcut alone is not enough.")
}

function Start-IrgsWebsite([int]$HostPort, [bool]$OpenBrowser, [int]$WaitSeconds) {
    $suiteFolder = $PSScriptRoot
    $hostFolder = Join-Path (Split-Path $suiteFolder -Parent) 'IRGS_Web'
    if ($AppRoot) { $hostFolder = $AppRoot }
    $hostEntry = Join-Path $hostFolder 'server.py'
    $suitePython = Resolve-IrgsPython
    $mutex = New-Object System.Threading.Mutex($false, "Local\IRGS-Core-3.3-Port-$HostPort")
    $held = $false
    try {
        try { $held = $mutex.WaitOne(45000) }
        catch [System.Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) { throw 'IRGS is already starting in another window. Please try again shortly.' }
        $state = Get-IrgsHostState $HostPort
        if ($state -eq 'Occupied') {
            throw "Another application is using port $HostPort. IRGS has left it running. Close that application or choose a different IRGS port, then try again."
        }
        Confirm-IrgsRelease $suitePython $suiteFolder
        # Verification may take time; recheck before deciding to launch.
        $state = Get-IrgsHostState $HostPort
        if ($state -eq 'Occupied') {
            throw "Another application is using port $HostPort. IRGS has left it running. Close that application or choose a different IRGS port, then try again."
        }
        if ($state -ne 'Ready') {
            $liveFolder = Join-Path $suiteFolder 'live'
            [System.IO.Directory]::CreateDirectory($liveFolder) | Out-Null
            $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + "-$PID"
            $stdout = Join-Path $liveFolder "host-$stamp-stdout.log"
            $stderr = Join-Path $liveFolder "host-$stamp-stderr.log"
            $arguments = @('-B', ('"' + $hostEntry + '"'), '--port', [string]$HostPort)
            $hostProcess = Start-Process -FilePath $suitePython -ArgumentList $arguments -WorkingDirectory $hostFolder `
                -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
            $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
            $state = 'Stopped'
            do {
                $state = Get-IrgsHostState $HostPort
                if ($state -eq 'Ready') { break }
                $hostProcess.Refresh()
                if ($hostProcess.HasExited) { break }
                Start-Sleep -Milliseconds 250
            } while ([DateTime]::UtcNow -lt $deadline)
            if ($state -ne 'Ready') {
                throw "IRGS did not become ready. No running application was stopped. Details are in $stderr"
            }
            $metadataPath = Join-Path $liveFolder 'host_process.json'
            $metadataTemp = $metadataPath + '.tmp'
            $metadata = @{entry = $hostEntry; process_id = $hostProcess.Id; port = $HostPort} | ConvertTo-Json
            [System.IO.File]::WriteAllText($metadataTemp, $metadata, (New-Object System.Text.UTF8Encoding($false)))
            Move-Item -LiteralPath $metadataTemp -Destination $metadataPath -Force
            Write-Host 'IRGS is ready. It will keep running after this window closes.'
        } else {
            Write-Host 'IRGS is already running. Reusing the existing website.'
        }
        $url = "http://127.0.0.1:$HostPort"
        if ($OpenBrowser) { Start-Process -FilePath $url }
        Write-Host $url
    } finally {
        if ($held) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

# Dot-sourcing exposes the read-only probe for launcher fixture tests.
if ($MyInvocation.InvocationName -ne '.') {
    try {
        Start-IrgsWebsite -HostPort $Port -OpenBrowser (-not $NoBrowser) -WaitSeconds $StartupWaitSeconds
        exit 0
    } catch {
        Write-Host ''
        Write-Host ('IRGS could not open: ' + $_.Exception.Message) -ForegroundColor Red
        exit 1
    }
}
