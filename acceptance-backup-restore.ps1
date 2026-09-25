[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProjectRoot = (Get-Location).Path,

    [Parameter()]
    [switch]$KeepTestEnvironment,

    [Parameter()]
    [switch]$SkipBuild,

    [Parameter()]
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter()][string[]]$Arguments = @(),
        [switch]$Capture,
        [switch]$AllowFailure
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 a natív stderr sorait PowerShell-hibává alakítja.
        # Continue mellett a teljes kimenet begyűjthető, az exit code-ot lent kezeljük.
        $ErrorActionPreference = "Continue"
        if ($Capture) {
            $output = @(& $File @Arguments 2>&1)
        }
        else {
            & $File @Arguments
            $output = @()
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (-not $AllowFailure -and $exitCode -ne 0) {
        $details = ($output | Out-String).Trim()
        throw "Parancs sikertelen ($exitCode): $File $($Arguments -join ' ')`n$details"
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $output }
}

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return [int]$listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

function New-RandomSecret {
    param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return ([Convert]::ToBase64String($buffer)).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ([string]$Actual -cne [string]$Expected) {
        throw "$Message. Elvart='$Expected', tenyleges='$Actual'"
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

$script:AcceptanceProject = $null
$script:ComposeFile = $null
$script:OverrideFile = $null
$script:FaultOverrideFile = $null
$script:AgentPort = 0
$script:BackendPort = 0
$script:AgentToken = $null

function Invoke-AcceptanceCompose {
    param(
        [Parameter()][string[]]$Arguments = @(),
        [switch]$Capture,
        [switch]$AllowFailure
    )
    $base = @(
        "compose", "-p", $script:AcceptanceProject,
        "-f", $script:ComposeFile,
        "-f", $script:OverrideFile
    )
    return Invoke-External -File "docker" -Arguments ($base + $Arguments) -Capture:$Capture -AllowFailure:$AllowFailure
}

function Invoke-AcceptanceComposeFault {
    param(
        [Parameter()][string[]]$Arguments = @(),
        [switch]$Capture,
        [switch]$AllowFailure
    )
    $base = @(
        "compose", "-p", $script:AcceptanceProject,
        "-f", $script:ComposeFile,
        "-f", $script:OverrideFile,
        "-f", $script:FaultOverrideFile
    )
    return Invoke-External -File "docker" -Arguments ($base + $Arguments) -Capture:$Capture -AllowFailure:$AllowFailure
}

function Invoke-AgentJson {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST", "PUT")][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter()]$Body = $null
    )
    $uri = "http://127.0.0.1:$($script:AgentPort)$Path"
    $headers = @{ "X-Backup-Agent-Token" = $script:AgentToken }
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30
    }
    $json = $Body | ConvertTo-Json -Depth 8 -Compress
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body $json -TimeoutSec 30
}

function Wait-Until {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Condition,
        [Parameter(Mandatory = $true)][string]$Description,
        [int]$Timeout = $TimeoutSeconds,
        [int]$DelayMilliseconds = 2000
    )
    $deadline = (Get-Date).AddSeconds($Timeout)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $result = & $Condition
            if ($result) {
                return $result
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
    $suffix = if ([string]::IsNullOrWhiteSpace([string]$lastError)) { "" } else { " Utolso hiba: $lastError" }
    throw "Idotullepes: $Description.$suffix"
}

function Wait-AgentReady {
    return Wait-Until -Description "backup-agent/pgBackRest inicializalas" -Condition {
        $status = Invoke-AgentJson -Method GET -Path "/status"
        if ($status.pgbackrest_ready -eq $true) { return $status }
        return $null
    }
}

function Wait-BackendReady {
    return Wait-Until -Description "backend health" -Condition {
        $health = Invoke-RestMethod -Method GET -Uri "http://127.0.0.1:$($script:BackendPort)/api/health" -TimeoutSec 10
        if ($health.status -eq "ok") { return $health }
        return $null
    }
}

function Wait-BackupJob {
    param([Parameter(Mandatory = $true)][string]$JobId)
    return Wait-Until -Description "backup job: $JobId" -Condition {
        $row = Invoke-AgentJson -Method GET -Path "/backups/$JobId"
        if ($row.status -eq "success") { return $row }
        if ($row.status -eq "failed") { throw "Backup sikertelen: $JobId - $($row.error)" }
        return $null
    }
}

function Wait-RestoreJob {
    param([Parameter(Mandatory = $true)][string]$RestoreId)
    return Wait-Until -Description "restore job: $RestoreId" -Condition {
        $row = Invoke-AgentJson -Method GET -Path "/restores/$RestoreId"
        if ($row.status -in @("success", "failed", "critical", "interrupted")) { return $row }
        return $null
    }
}

function Invoke-DbSql {
    param([Parameter(Mandatory = $true)][string]$Sql)
    Invoke-AcceptanceCompose -Arguments @(
        "exec", "-T", "db", "psql",
        "-U", "workapp", "-d", "workapp", "-v", "ON_ERROR_STOP=1", "-c", $Sql
    ) | Out-Null
}

function Get-DbScalar {
    param([Parameter(Mandatory = $true)][string]$Sql)
    $result = Invoke-AcceptanceCompose -Arguments @(
        "exec", "-T", "db", "psql",
        "-U", "workapp", "-d", "workapp", "-Atq", "-c", $Sql
    ) -Capture
    return (($result.Output | Out-String).Trim())
}

function Set-ProbeState {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value -notmatch '^[A-Za-z0-9_-]+$') {
        throw "Az acceptance probe csak egyszeru ASCII erteket fogad el."
    }
    Invoke-DbSql -Sql "INSERT INTO backup_acceptance_probe(id, probe_value) VALUES (1, '$Value') ON CONFLICT (id) DO UPDATE SET probe_value=EXCLUDED.probe_value;"
    Invoke-AcceptanceCompose -Arguments @(
        "exec", "-T", "backend", "sh", "-lc",
        "printf '%s' '$Value' > /app/runtime/acceptance-probe.txt"
    ) | Out-Null
}

function Assert-ProbeState {
    param([Parameter(Mandatory = $true)][string]$Expected)
    $dbValue = Get-DbScalar -Sql "SELECT probe_value FROM backup_acceptance_probe WHERE id=1;"
    $runtimeResult = Invoke-AcceptanceCompose -Arguments @(
        "exec", "-T", "backend", "sh", "-lc", "cat /app/runtime/acceptance-probe.txt"
    ) -Capture
    $runtimeValue = (($runtimeResult.Output | Out-String).Trim())
    Assert-Equal -Actual $dbValue -Expected $Expected -Message "DB acceptance probe elter"
    Assert-Equal -Actual $runtimeValue -Expected $Expected -Message "Runtime acceptance probe elter"
}

function Start-MasterBackup {
    $created = Invoke-AgentJson -Method POST -Path "/backups/master" -Body @{
        requested_by_name = "Automatikus acceptance teszt"
        requested_by_email = "acceptance@example.com"
    }
    $row = Wait-BackupJob -JobId ([string]$created.job_id)
    Assert-Equal -Actual $row.effective_kind -Expected "master" -Message "A manualis MASTER nem MASTER-kent keszult el"
    return $row
}

function Start-IncrementalBackup {
    # Windows PowerShell 5.1 a natív programnak átadott argumentumból eltávolíthatja
    # a beágyazott dupla idézőjeleket. A Python literálok ezért egyszeres idézőjelesek.
    $code = "import json, agent; agent.init_db(); job_id = agent.insert_backup_job('incremental', 'acceptance'); agent.perform_job(job_id); print(json.dumps(agent.list_jobs(1)[0], ensure_ascii=True))"
    $result = Invoke-AcceptanceCompose -Arguments @("exec", "-T", "backup-agent", "python", "-c", $code) -Capture
    $lines = @(($result.Output | ForEach-Object { [string]$_ }) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($lines.Count -eq 0) {
        throw "Az inkrementalis acceptance backup nem adott vissza eredmenyt."
    }
    $row = $lines[-1] | ConvertFrom-Json
    if ($row.status -ne "success") {
        throw "Az inkrementalis acceptance backup sikertelen: $($row.error)"
    }
    Assert-Equal -Actual $row.effective_kind -Expected "incremental" -Message "A MASTER utan inditott teszt backup nem inkrementalis lett"
    return $row
}

function Validate-BackupPoint {
    param([Parameter(Mandatory = $true)][string]$BackupId)
    $validation = Invoke-AgentJson -Method POST -Path "/backups/$BackupId/validate" -Body @{}
    Assert-True -Condition ($validation.valid -eq $true) -Message "A backup validacio nem adott valid=true eredmenyt: $BackupId"
    Assert-True -Condition ($validation.pgbackrest_verified -eq $true) -Message "A pgBackRest verify nem futott le: $BackupId"
    return $validation
}

function Start-Restore {
    param([Parameter(Mandatory = $true)][string]$BackupId)
    $created = Invoke-AgentJson -Method POST -Path "/backups/$BackupId/restore" -Body @{
        confirmation = "VISSZAALLIT"
        requested_by_name = "Automatikus acceptance teszt"
        requested_by_email = "acceptance@example.com"
    }
    return Wait-RestoreJob -RestoreId ([string]$created.restore_id)
}

$OriginalLocation = (Get-Location).Path
$OriginalComposeProjectName = $env:COMPOSE_PROJECT_NAME
$Succeeded = $false
$TestRoot = $null
$TestProjectRoot = $null

try {
    $resolvedSource = (Resolve-Path -LiteralPath $ProjectRoot).Path
    foreach ($required in @("docker-compose.yml", ".env.example", "VERSION", "backup-munkalap-app.ps1", "restore-munkalap-app.ps1")) {
        if (-not (Test-Path -LiteralPath (Join-Path $resolvedSource $required) -PathType Leaf)) {
            throw "Hianyzik a szukseges projektfajl: $required"
        }
    }

    Invoke-External -File "docker" -Arguments @("version") | Out-Null
    Invoke-External -File "docker" -Arguments @("compose", "version") | Out-Null

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $suffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    $script:AcceptanceProject = "munkalap-acceptance-$suffix"
    $TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "munkalap-backup-acceptance-$stamp-$suffix"
    $TestProjectRoot = Join-Path $TestRoot "project"
    New-Item -ItemType Directory -Path $TestProjectRoot -Force | Out-Null

    Write-Host "Acceptance forras masolasa: $TestProjectRoot"
    $excludedNames = @(".git", "node_modules", "backups", "pre-restore-backups", ".acceptance")
    Get-ChildItem -LiteralPath $resolvedSource -Force | Where-Object {
        $_.Name -notin $excludedNames -and $_.Extension -ne ".zip"
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $TestProjectRoot -Recurse -Force
    }

    $script:ComposeFile = Join-Path $TestProjectRoot "docker-compose.yml"
    $script:OverrideFile = Join-Path $TestProjectRoot "docker-compose.acceptance.yml"
    $script:FaultOverrideFile = Join-Path $TestProjectRoot "docker-compose.acceptance-fault.yml"
    $script:AgentPort = Get-FreeTcpPort
    $script:BackendPort = Get-FreeTcpPort
    $appPort = Get-FreeTcpPort
    $postgresPort = Get-FreeTcpPort
    $script:AgentToken = New-RandomSecret -Bytes 36
    $secretKey = New-RandomSecret -Bytes 48

    @"
APP_VERSION=0.31.0
POSTGRES_DB=workapp
POSTGRES_USER=workapp
POSTGRES_PASSWORD=AcceptanceOnly_$(New-RandomSecret -Bytes 18)
POSTGRES_PORT=$postgresPort
BACKEND_PORT=$($script:BackendPort)
APP_PORT=$appPort
SECRET_KEY=$secretKey
BACKEND_WORKERS=1
DATABASE_POOL_SIZE=2
DATABASE_MAX_OVERFLOW=2
BACKUP_AGENT_TOKEN=$($script:AgentToken)
BACKUP_TIMEZONE=Europe/Budapest
"@ | Set-Content -LiteralPath (Join-Path $TestProjectRoot ".env") -Encoding Ascii

    @"
services:
  db:
    ports:
      - "127.0.0.1:$postgresPort:5432"
  backend:
    ports:
      - "127.0.0.1:$($script:BackendPort):8000"
  backup-agent:
    ports:
      - "127.0.0.1:$($script:AgentPort):8090"
"@ | Set-Content -LiteralPath $script:OverrideFile -Encoding Ascii

    @"
services:
  backend:
    environment:
      BACKUP_AGENT_TOKEN: acceptance-intentional-wrong-token
"@ | Set-Content -LiteralPath $script:FaultOverrideFile -Encoding Ascii

    Set-Location -LiteralPath $TestProjectRoot
    Write-Host ""
    Write-Host "Izolalt Compose projekt: $($script:AcceptanceProject)"
    Write-Host "Tesztkonyvtar: $TestRoot"
    Write-Host ""

    Invoke-AcceptanceCompose -Arguments @("config", "--quiet") | Out-Null
    if (-not $SkipBuild) {
        Write-Host "1/10 Izolalt image-ek buildelese..."
        Invoke-AcceptanceCompose -Arguments @("build", "db", "backup-agent", "backend", "frontend") | Out-Null
    }
    else {
        Write-Host "1/10 Build kihagyva a -SkipBuild kapcsolo miatt."
    }

    Write-Host "2/10 Izolalt stack inditasa..."
    Invoke-AcceptanceCompose -Arguments @("up", "-d", "db", "backup-agent", "backend", "frontend") | Out-Null
    Wait-AgentReady | Out-Null
    Wait-BackendReady | Out-Null

    $heads = Invoke-AcceptanceCompose -Arguments @("exec", "-T", "backend", "alembic", "heads") -Capture
    $headLines = @(($heads.Output | ForEach-Object { ([string]$_).Trim() }) | Where-Object { $_ })
    Assert-Equal -Actual $headLines.Count -Expected 1 -Message "Az acceptance stackben nem pontosan egy Alembic head van"
    Assert-True -Condition ($headLines[0] -like "0029_cloud_security*") -Message "Varatlan Alembic head: $($headLines[0])"

    Invoke-DbSql -Sql "CREATE TABLE IF NOT EXISTS backup_acceptance_probe(id integer PRIMARY KEY, probe_value text NOT NULL);"

    Write-Host "3/10 MASTER mentés + fizikai pgBackRest verify..."
    Set-ProbeState -Value "master-state"
    $master = Start-MasterBackup
    Validate-BackupPoint -BackupId ([string]$master.id) | Out-Null

    Write-Host "4/10 Inkrementalis mentés + runtime delta + pgBackRest verify..."
    Set-ProbeState -Value "incremental-state"
    $incremental = Start-IncrementalBackup
    Validate-BackupPoint -BackupId ([string]$incremental.id) | Out-Null

    Write-Host "5/10 MASTER mentési pontra webes/fizikai restore..."
    Set-ProbeState -Value "after-incremental"
    $restoreMaster = Start-Restore -BackupId ([string]$master.id)
    Assert-Equal -Actual $restoreMaster.status -Expected "success" -Message "MASTER restore sikertelen"
    Assert-True -Condition (-not [string]::IsNullOrWhiteSpace([string]$restoreMaster.pre_restore_backup_id)) -Message "A MASTER restore pre-restore mentése hianyzik"
    Assert-True -Condition (-not [string]::IsNullOrWhiteSpace([string]$restoreMaster.post_restore_backup_id)) -Message "A MASTER restore post-restore mentése hianyzik"
    Wait-BackendReady | Out-Null
    Assert-ProbeState -Expected "master-state"

    Write-Host "6/10 Inkrementalis mentési pontra webes/fizikai restore..."
    $restoreIncremental = Start-Restore -BackupId ([string]$incremental.id)
    Assert-Equal -Actual $restoreIncremental.status -Expected "success" -Message "Inkrementalis restore sikertelen"
    Wait-BackendReady | Out-Null
    Assert-ProbeState -Expected "incremental-state"

    Write-Host "7/10 Automatikus rollback fizikai acceptance teszt..."
    Set-ProbeState -Value "rollback-origin"
    Invoke-AcceptanceComposeFault -Arguments @("up", "-d", "--no-deps", "--force-recreate", "backend") | Out-Null
    Wait-BackendReady | Out-Null
    $rollbackRestore = Start-Restore -BackupId ([string]$master.id)
    Assert-Equal -Actual $rollbackRestore.status -Expected "failed" -Message "A szandekosan hibas restore-nak failed allapotban kellett volna zarulnia"
    Assert-Equal -Actual $rollbackRestore.rollback_status -Expected "success" -Message "Az automatikus rollback nem volt sikeres"
    Assert-True -Condition (-not [string]::IsNullOrWhiteSpace([string]$rollbackRestore.rollback_restore_backup_id)) -Message "A rollback MASTER azonosito hianyzik"
    $agentAfterRollback = Invoke-AgentJson -Method GET -Path "/status"
    Assert-True -Condition ($agentAfterRollback.restore_recovery_required -ne $true) -Message "Sikeres rollback utan recovery lock maradt"
    Assert-ProbeState -Expected "rollback-origin"

    Write-Host "8/10 Backend normal tokennel ujra letrehozasa..."
    Invoke-AcceptanceCompose -Arguments @("up", "-d", "--no-deps", "--force-recreate", "backend") | Out-Null
    Wait-BackendReady | Out-Null

    Write-Host "9/10 Host PowerShell MASTER + disaster-recovery restore..."
    $hostBackupRoot = Join-Path $TestRoot "host-backups"
    New-Item -ItemType Directory -Path $hostBackupRoot -Force | Out-Null
    $env:COMPOSE_PROJECT_NAME = $script:AcceptanceProject
    & (Join-Path $TestProjectRoot "backup-munkalap-app.ps1") -ProjectRoot $TestProjectRoot -OutputRoot $hostBackupRoot
    $hostBackup = @(
        Get-ChildItem -LiteralPath $hostBackupRoot -Directory -Filter "backup-*" |
            Sort-Object LastWriteTime -Descending
    ) | Select-Object -First 1
    if ($null -eq $hostBackup) {
        throw "A host MASTER acceptance mentési konyvtara nem talalhato."
    }
    Set-ProbeState -Value "host-mutated"
    & (Join-Path $TestProjectRoot "restore-munkalap-app.ps1") -BackupDir $hostBackup.FullName -ProjectRoot $TestProjectRoot -Force
    # A host restore szandekosan a mentett alap Compose fajlt allitja vissza,
    # amelyben az acceptance-only backup-agent host port nincs publikalva.
    # Ujra alkalmazzuk a teszt override-ot az izolalt projektre.
    Invoke-AcceptanceCompose -Arguments @("up", "-d", "--no-build", "backup-agent", "backend", "frontend") | Out-Null
    Wait-AgentReady | Out-Null
    Wait-BackendReady | Out-Null
    Assert-ProbeState -Expected "rollback-origin"

    Write-Host "10/10 Vegso integritas- es migracioellenorzes..."
    $finalMaster = Start-MasterBackup
    Validate-BackupPoint -BackupId ([string]$finalMaster.id) | Out-Null
    $current = Invoke-AcceptanceCompose -Arguments @("exec", "-T", "backend", "alembic", "current") -Capture
    $currentText = ($current.Output | Out-String).Trim()
    Assert-True -Condition ($currentText -like "*0029_cloud_security*") -Message "A vegso Alembic current elter a vart headtol"

    $Succeeded = $true
    Write-Host ""
    Write-Host "ACCEPTANCE SIKERES"
    Write-Host "- MASTER backup + pgBackRest verify: OK"
    Write-Host "- Inkrementalis backup + runtime delta: OK"
    Write-Host "- MASTER restore: OK"
    Write-Host "- Inkrementalis restore: OK"
    Write-Host "- Destruktiv hiba utani automatikus rollback: OK"
    Write-Host "- Host PowerShell backup/restore: OK"
    Write-Host "- Alembic egyetlen head/current: OK"
}
finally {
    if ($null -eq $OriginalComposeProjectName) {
        Remove-Item Env:COMPOSE_PROJECT_NAME -ErrorAction SilentlyContinue
    }
    else {
        $env:COMPOSE_PROJECT_NAME = $OriginalComposeProjectName
    }
    Set-Location -LiteralPath $OriginalLocation

    if ($Succeeded -and -not $KeepTestEnvironment -and -not [string]::IsNullOrWhiteSpace([string]$script:AcceptanceProject)) {
        if ($script:AcceptanceProject -like "munkalap-acceptance-*") {
            try {
                Write-Host "Izolalt acceptance stack es teszt-volume-ok torlese..."
                Invoke-AcceptanceCompose -Arguments @("down", "--remove-orphans", "--volumes") -AllowFailure | Out-Null
            }
            catch {
                Write-Warning "Az acceptance kornyezet automatikus takaritasa sikertelen: $($_.Exception.Message)"
            }
            if (-not [string]::IsNullOrWhiteSpace([string]$TestRoot) -and (Test-Path -LiteralPath $TestRoot)) {
                try { Remove-Item -LiteralPath $TestRoot -Recurse -Force } catch { Write-Warning "A tesztkonyvtar nem torolheto: $TestRoot" }
            }
        }
        else {
            Write-Warning "Biztonsagi okbol nem toroltem volume-okat, mert a projektnev nem acceptance prefixu: $($script:AcceptanceProject)"
        }
    }
    elseif (-not $Succeeded -and -not [string]::IsNullOrWhiteSpace([string]$TestRoot)) {
        Write-Warning "Az acceptance teszt hibaval leallt. A diagnosztikai kornyezetet nem toroltem."
        Write-Warning "Compose projekt: $($script:AcceptanceProject)"
        Write-Warning "Tesztkonyvtar: $TestRoot"
    }
}
