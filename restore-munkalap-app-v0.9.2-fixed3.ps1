[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir,

    [Parameter()]
    [string]$ProjectRoot = (Get-Location).Path,

    [Parameter()]
    [string]$SafetyBackupScript = "",

    [Parameter()]
    [switch]$SkipSafetyBackup,

    [Parameter()]
    [switch]$ValidateOnly,

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$ResumeInterruptedRestore
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$ErrorMessage,

        [switch]$CaptureOutput,

        [switch]$AllowFailure
    )

    # A Docker es egyes konteneres parancsok (peldaul Alembic) normal INFO
    # uzeneteket is a standard hibakimenetre irhatnak. PowerShell 7-ben,
    # illetve 2>&1 atiranyitas mellett ez ErrorRecord-da alakulhat, es a
    # globalis Stop beallitas akkor is megszakithatja a scriptet, ha a native
    # folyamat valojaban 0-s hibakoddal fejezodott be. Ezert a native folyamat
    # idejere kikapcsoljuk ezt a PowerShell-viselkedest, es kizarolag a tenyleges
    # process exit code alapjan dontunk a sikerrol.
    $previousErrorActionPreference = $ErrorActionPreference
    $nativePreferenceVariable = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
    $previousNativePreference = $null

    try {
        $ErrorActionPreference = "Continue"

        if ($null -ne $nativePreferenceVariable) {
            $previousNativePreference = $PSNativeCommandUseErrorActionPreference
            $PSNativeCommandUseErrorActionPreference = $false
        }

        if ($CaptureOutput) {
            $output = @(& docker @Arguments 2>&1)
            $exitCode = $LASTEXITCODE

            if (-not $AllowFailure -and $exitCode -ne 0) {
                $details = ($output | ForEach-Object { [string]$_ } | Out-String).Trim()
                throw "$ErrorMessage (Docker hibakod: $exitCode)`n$details"
            }

            return [pscustomobject]@{
                ExitCode = $exitCode
                Output = $output
            }
        }

        & docker @Arguments
        $exitCode = $LASTEXITCODE

        if (-not $AllowFailure -and $exitCode -ne 0) {
            throw "$ErrorMessage (Docker hibakod: $exitCode)"
        }

        return $exitCode
    }
    finally {
        if ($null -ne $nativePreferenceVariable) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Assert-NonEmptyFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "A szukseges fajl nem talalhato: $Path"
    }

    if ((Get-Item -LiteralPath $Path).Length -le 0) {
        throw "A szukseges fajl ures: $Path"
    }
}

function Get-ComposeContainerIds {
    param(
        [string]$Project = "",
        [Parameter(Mandatory = $true)][string]$Service,
        [switch]$IncludeStopped
    )

    $args = @("compose")
    if (-not [string]::IsNullOrWhiteSpace($Project)) {
        $args += @("-p", $Project)
    }
    $args += "ps"
    if ($IncludeStopped) {
        $args += "-a"
    }
    $args += @("-q", $Service)

    $result = Invoke-Docker -Arguments $args -ErrorMessage "A(z) '$Service' kontener lekerdezese sikertelen." -CaptureOutput

    return @(
        $result.Output |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

function Get-ContainerComposeProject {
    param([Parameter(Mandatory = $true)][string]$ContainerId)

    $result = Invoke-Docker -Arguments @("inspect", $ContainerId) -ErrorMessage "A kontener vizsgalata sikertelen: $ContainerId" -CaptureOutput
    $json = ($result.Output | Out-String) | ConvertFrom-Json

    if ($null -eq $json -or $json.Count -eq 0) {
        throw "Ures docker inspect valasz: $ContainerId"
    }

    return [string]$json[0].Config.Labels.'com.docker.compose.project'
}

function Get-ProjectComposeServices {
    param([Parameter(Mandatory = $true)][string]$Project)

    $result = Invoke-Docker -Arguments @(
        "ps", "-a",
        "--filter", "label=com.docker.compose.project=$Project",
        "--format", "{{.ID}}"
    ) -ErrorMessage "A Compose projekthez tartozo kontenerek lekerdezese sikertelen." -CaptureOutput

    $containerIds = @(
        $result.Output |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )

    $services = @()
    foreach ($containerId in $containerIds) {
        $inspectResult = Invoke-Docker -Arguments @("inspect", $containerId) -ErrorMessage "A kontener vizsgalata sikertelen: $containerId" -CaptureOutput
        $inspectJson = ($inspectResult.Output | Out-String) | ConvertFrom-Json
        if ($null -ne $inspectJson -and $inspectJson.Count -gt 0) {
            $service = [string]$inspectJson[0].Config.Labels.'com.docker.compose.service'
            if (-not [string]::IsNullOrWhiteSpace($service)) {
                $services += $service
            }
        }
    }

    return @($services | Sort-Object -Unique)
}

function Test-BackupChecksums {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$ChecksumFile
    )

    Assert-NonEmptyFile -Path $ChecksumFile

    $checked = 0
    foreach ($line in Get-Content -LiteralPath $ChecksumFile) {
        $text = ([string]$line).Trim()
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }

        if ($text -notmatch '^([0-9a-fA-F]{64}) \*(.+)$') {
            throw "Ervenytelen sor a checksums.sha256 fajlban: $text"
        }

        $expectedHash = $Matches[1].ToLowerInvariant()
        $relativeName = $Matches[2]
        $filePath = Join-Path $Directory $relativeName

        Assert-NonEmptyFile -Path $filePath

        $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw "SHA-256 elteres: $relativeName`nElvart: $expectedHash`nTenyleges: $actualHash"
        }

        $checked++
    }

    if ($checked -eq 0) {
        throw "A checksums.sha256 nem tartalmaz ellenorizheto fajlt."
    }

    Write-Host "SHA-256 ellenorzes sikeres: $checked fajl."
}

function Wait-ForDatabase {
    param(
        [Parameter(Mandatory = $true)][string]$Project,
        [int]$Attempts = 60,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $result = Invoke-Docker -Arguments @(
            "compose", "-p", $Project,
            "exec", "-T", "db",
            "sh", "-lc",
            'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
        ) -ErrorMessage "Az adatbazis keszenleti ellenorzese sikertelen." -CaptureOutput -AllowFailure

        if ($result.ExitCode -eq 0) {
            return
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Az adatbazis nem valt elerhetove a megadott idon belul."
}

function Wait-ForBackend {
    param(
        [Parameter(Mandatory = $true)][string]$Project,
        [int]$Attempts = 60,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $result = Invoke-Docker -Arguments @(
            "compose", "-p", $Project,
            "exec", "-T", "backend",
            "alembic", "current"
        ) -ErrorMessage "A backend migracios allapotanak ellenorzese sikertelen." -CaptureOutput -AllowFailure

        if ($result.ExitCode -eq 0) {
            $lines = @(
                $result.Output |
                    ForEach-Object { ([string]$_).Trim() } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            )
            if ($lines.Count -gt 0) {
                Write-Host "Alembic ellenorzes sikeres:"
                $lines | ForEach-Object { Write-Host "  $_" }
            }
            return
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "A backend nem indult el vagy az Alembic ellenorzes nem sikerult."
}

$OriginalLocation = (Get-Location).Path
$RestoreError = $null
$RestoreSucceeded = $false
$Project = $null
$DbContainerDumpPath = "/tmp/munkalap-restore.dump"
$DbContainerResetSqlPath = "/tmp/munkalap-reset-schema.sql"
$DbContainerCountSqlPath = "/tmp/munkalap-counts.sql"
$ResolvedBackupDir = $null
$ResolvedProjectRoot = $null
$SafetyBackupDir = $null
$DumpCopiedToContainer = $false
$ResetSqlCopiedToContainer = $false
$CountSqlCopiedToContainer = $false
$HostResetSqlPath = $null
$HostCountSqlPath = $null

try {
    $ResolvedBackupDir = (Resolve-Path -LiteralPath $BackupDir).Path
    $ResolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

    Set-Location -LiteralPath $ResolvedProjectRoot

    $ManifestPath = Join-Path $ResolvedBackupDir "manifest.json"
    $ChecksumPath = Join-Path $ResolvedBackupDir "checksums.sha256"

    Assert-NonEmptyFile -Path $ManifestPath
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json

    if ($Manifest.format -ne "munkalap-app-host-backup") {
        throw "Nem tamogatott mentesi formatum: $($Manifest.format)"
    }

    if ([int]$Manifest.format_version -ne 1) {
        throw "Nem tamogatott mentesi formatumverzio: $($Manifest.format_version)"
    }

    $Project = [string]$Manifest.compose_project
    if ([string]::IsNullOrWhiteSpace($Project)) {
        throw "A manifest nem tartalmaz Compose projektnevet."
    }

    $DbDumpPath = Join-Path $ResolvedBackupDir ([string]$Manifest.files.database_dump)
    $RuntimeTarPath = Join-Path $ResolvedBackupDir ([string]$Manifest.files.app_runtime)
    $ImagesTarPath = Join-Path $ResolvedBackupDir ([string]$Manifest.files.docker_images)
    $BackupComposePath = Join-Path $ResolvedBackupDir ([string]$Manifest.files.compose)
    $BackupEnvPath = Join-Path $ResolvedBackupDir ([string]$Manifest.files.environment)
    $BackupVersionPath = Join-Path $ResolvedBackupDir "VERSION"
    $RuntimeTarName = [System.IO.Path]::GetFileName($RuntimeTarPath)

    foreach ($path in @(
        $DbDumpPath,
        $RuntimeTarPath,
        $ImagesTarPath,
        $BackupComposePath,
        $BackupEnvPath,
        $BackupVersionPath
    )) {
        Assert-NonEmptyFile -Path $path
    }

    Write-Host "Mentés ellenorzese..."
    Write-Host "  Konyvtar: $ResolvedBackupDir"
    Write-Host "  Alkalmazasverzio: $($Manifest.application_version)"
    Write-Host "  Mentés ideje: $($Manifest.created_at)"
    Write-Host "  Compose projekt: $Project"

    Test-BackupChecksums -Directory $ResolvedBackupDir -ChecksumFile $ChecksumPath

    if ($ValidateOnly) {
        Write-Host ""
        Write-Host "A mentés ervenyes. A ValidateOnly kapcsolo miatt nem tortent visszaallitas."
        return
    }

    Invoke-Docker -Arguments @("version") -ErrorMessage "A Docker nem erheto el." | Out-Null
    Invoke-Docker -Arguments @("compose", "version") -ErrorMessage "A Docker Compose nem erheto el." | Out-Null

    $currentServices = @(Get-ProjectComposeServices -Project $Project)
    $requiredServices = @("db", "backend", "frontend")
    $hasCurrentDeployment = (@($requiredServices | Where-Object { $_ -notin $currentServices }).Count -eq 0)
    $hasPartialDeployment = ($currentServices.Count -gt 0 -and -not $hasCurrentDeployment)

    if ($hasPartialDeployment -and -not $ResumeInterruptedRestore) {
        $serviceText = if ($currentServices.Count -gt 0) { $currentServices -join ", " } else { "nincs" }
        throw "Reszleges Compose telepites talalhato a '$Project' projektben ($serviceText). Ez lehet egy korabban megszakadt visszaallitas. Ellenorizd az allapotot, majd csak tudatosan hasznald a -ResumeInterruptedRestore kapcsolot."
    }

    if ($hasPartialDeployment -and $ResumeInterruptedRestore) {
        Write-Warning "Megszakadt visszaallitas folytatasa: jelenlegi szolgaltatasok: $($currentServices -join ', '). Veszmentes nem keszul a reszleges celrendszerrol."
    }

    if (-not $Force) {
        Write-Host ""
        Write-Warning "A visszaallitas FELULIRJA a jelenlegi adatbazist, runtime fajlokat es telepitesi konfiguraciot."
        $confirmation = Read-Host "A folytatashoz gepeld be pontosan: VISSZAALLIT"
        if ($confirmation -cne "VISSZAALLIT") {
            throw "A visszaallitas megszakitva: hibas megerosites."
        }
    }

    if ($hasCurrentDeployment -and -not $SkipSafetyBackup) {
        if ([string]::IsNullOrWhiteSpace($SafetyBackupScript)) {
            $candidates = @(
                (Join-Path $ResolvedProjectRoot "backup-munkalap-app-v0.9.2-fixed.ps1"),
                (Join-Path $ResolvedProjectRoot "backup-munkalap-app-v0.9.1.ps1")
            )
            $SafetyBackupScript = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }) | Select-Object -First 1
        }

        if ([string]::IsNullOrWhiteSpace($SafetyBackupScript) -or -not (Test-Path -LiteralPath $SafetyBackupScript -PathType Leaf)) {
            throw "A visszaallitas elotti veszmentes scriptje nem talalhato. Add meg a -SafetyBackupScript parametert, vagy csak tudatosan hasznald a -SkipSafetyBackup kapcsolot."
        }

        $SafetyRoot = Join-Path $ResolvedProjectRoot "pre-restore-backups"
        New-Item -ItemType Directory -Path $SafetyRoot -Force | Out-Null

        Write-Host ""
        Write-Host "Visszaallitas elotti veszmentes keszitese..."
        $safetyStartedAt = Get-Date

        $previousComposeProjectName = $env:COMPOSE_PROJECT_NAME
        try {
            $env:COMPOSE_PROJECT_NAME = $Project
            & $SafetyBackupScript -ProjectRoot $ResolvedProjectRoot -OutputRoot $SafetyRoot
        }
        finally {
            $env:COMPOSE_PROJECT_NAME = $previousComposeProjectName
        }

        $SafetyBackupDir = @(
            Get-ChildItem -LiteralPath $SafetyRoot -Directory -Filter "backup-*" |
                Where-Object { $_.LastWriteTime -ge $safetyStartedAt.AddSeconds(-2) } |
                Sort-Object LastWriteTime -Descending
        ) | Select-Object -First 1

        if ($null -eq $SafetyBackupDir) {
            throw "A veszmentes lefutott, de a mentési konyvtar nem talalhato."
        }

        $SafetyBackupDir = $SafetyBackupDir.FullName
        Write-Host "Veszmentes: $SafetyBackupDir"
    }
    elseif ($hasCurrentDeployment -and $SkipSafetyBackup) {
        Write-Warning "A visszaallitas elotti veszmentest tudatosan kihagytad."
    }
    elseif ($hasPartialDeployment -and $ResumeInterruptedRestore) {
        Write-Host "Reszleges, megszakadt celrendszer folytatasa; veszmentes nem keszul."
    }
    else {
        Write-Host "Nem talalhato jelenlegi teljes Compose telepites; veszmentes nem szukseges."
    }

    Write-Host ""
    Write-Host "1/9 Jelenlegi szolgaltatasok leallitasa (volume torles nelkul)..."
    Invoke-Docker -Arguments @("compose", "-p", $Project, "down", "--remove-orphans") -ErrorMessage "A jelenlegi Compose szolgaltatasok leallitasa sikertelen." | Out-Null

    Write-Host "2/9 Mentett image-ek visszatoltese..."
    Invoke-Docker -Arguments @("image", "load", "--input", $ImagesTarPath) -ErrorMessage "A Docker image-ek visszatoltese sikertelen." | Out-Null

    foreach ($imageRef in @(
        [string]$Manifest.services.db.image,
        [string]$Manifest.services.backend.image,
        [string]$Manifest.services.frontend.image
    )) {
        if ([string]::IsNullOrWhiteSpace($imageRef)) {
            throw "A manifest egyik image-hivatkozasa ures."
        }
        Invoke-Docker -Arguments @("image", "inspect", $imageRef) -ErrorMessage "A visszatoltott image nem talalhato: $imageRef" | Out-Null
    }

    Write-Host "3/9 Telepitesi konfiguracio visszaallitasa..."
    Copy-Item -LiteralPath $BackupComposePath -Destination (Join-Path $ResolvedProjectRoot "docker-compose.yml") -Force
    Copy-Item -LiteralPath $BackupEnvPath -Destination (Join-Path $ResolvedProjectRoot ".env") -Force
    Copy-Item -LiteralPath $BackupVersionPath -Destination (Join-Path $ResolvedProjectRoot "VERSION") -Force

    $backupChangeLog = Join-Path $ResolvedBackupDir "CHANGELOG.md"
    if (Test-Path -LiteralPath $backupChangeLog -PathType Leaf) {
        Copy-Item -LiteralPath $backupChangeLog -Destination (Join-Path $ResolvedProjectRoot "CHANGELOG.md") -Force
    }

    Invoke-Docker -Arguments @("compose", "-p", $Project, "config", "--quiet") -ErrorMessage "A visszaallitott Compose konfiguracio ervenytelen." | Out-Null

    Write-Host "4/9 Adatbazis inditasa..."
    Invoke-Docker -Arguments @("compose", "-p", $Project, "up", "-d", "--no-build", "db") -ErrorMessage "Az adatbazis inditasa sikertelen." | Out-Null
    Wait-ForDatabase -Project $Project

    Write-Host "5/9 PostgreSQL dump es runtime TAR elozetes ellenorzese..."
    Invoke-Docker -Arguments @("compose", "-p", $Project, "cp", $DbDumpPath, "db:$DbContainerDumpPath") -ErrorMessage "A PostgreSQL dump bemasolasa sikertelen." | Out-Null
    $DumpCopiedToContainer = $true

    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "exec", "-T", "db",
        "sh", "-lc",
        ('pg_restore --list "' + $DbContainerDumpPath + '" >/dev/null')
    ) -ErrorMessage "A PostgreSQL dump belso ellenorzese sikertelen." | Out-Null

    $runtimeMount = "${ResolvedBackupDir}:/restore:ro"
    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "run", "--rm", "-T", "--no-deps",
        "-v", $runtimeMount,
        "--entrypoint", "sh", "backend",
        "-lc", ('tar -tzf "/restore/' + $RuntimeTarName + '" >/dev/null')
    ) -ErrorMessage "Az app_runtime TAR belso ellenorzese sikertelen." | Out-Null

    Write-Host "6/9 PostgreSQL adatbazis visszaallitasa..."

    # Az SQL-t fajlon keresztul futtatjuk. Ez elkeruli a Windows PowerShell,
    # a Docker CLI es a kontener shell kozotti tobbszoros idezojelezesi hibakat.
    $HostResetSqlPath = Join-Path ([System.IO.Path]::GetTempPath()) (
        "munkalap-reset-schema-" + [Guid]::NewGuid().ToString("N") + ".sql"
    )
    @(
        "DROP SCHEMA IF EXISTS public CASCADE;",
        "CREATE SCHEMA public;"
    ) | Set-Content -LiteralPath $HostResetSqlPath -Encoding Ascii

    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "cp", $HostResetSqlPath, "db:$DbContainerResetSqlPath"
    ) -ErrorMessage "A sema-visszaallito SQL bemasolasa sikertelen." | Out-Null
    $ResetSqlCopiedToContainer = $true

    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "exec", "-T", "db",
        "sh", "-lc",
        ('psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "' + $DbContainerResetSqlPath + '"')
    ) -ErrorMessage "A jelenlegi adatbazisséma torlese sikertelen." | Out-Null

    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "exec", "-T", "db",
        "sh", "-lc",
        ('pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error "' + $DbContainerDumpPath + '"')
    ) -ErrorMessage "A PostgreSQL adatbazis visszaallitasa sikertelen." | Out-Null

    Write-Host "7/9 app_runtime volume visszaallitasa..."
    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "run", "--rm", "-T", "--no-deps",
        "-v", $runtimeMount,
        "--entrypoint", "sh", "backend",
        "-lc", ('find /app/runtime -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf "/restore/' + $RuntimeTarName + '" -C /app/runtime')
    ) -ErrorMessage "Az app_runtime volume visszaallitasa sikertelen." | Out-Null

    Write-Host "8/9 Backend es frontend inditasa..."
    Invoke-Docker -Arguments @("compose", "-p", $Project, "up", "-d", "--no-build", "backend", "frontend") -ErrorMessage "A backend/frontend inditasa sikertelen." | Out-Null
    Wait-ForBackend -Project $Project

    Write-Host "9/9 Visszaallitott rendszer ellenorzese..."

    $HostCountSqlPath = Join-Path ([System.IO.Path]::GetTempPath()) (
        "munkalap-counts-" + [Guid]::NewGuid().ToString("N") + ".sql"
    )
    @(
        "SELECT (SELECT COUNT(*) FROM users),",
        "       (SELECT COUNT(*) FROM customers),",
        "       (SELECT COUNT(*) FROM assets),",
        "       (SELECT COUNT(*) FROM work_orders),",
        "       (SELECT COUNT(*) FROM work_order_archives);"
    ) | Set-Content -LiteralPath $HostCountSqlPath -Encoding Ascii

    Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "cp", $HostCountSqlPath, "db:$DbContainerCountSqlPath"
    ) -ErrorMessage "A rekordszam-ellenorzo SQL bemasolasa sikertelen." | Out-Null
    $CountSqlCopiedToContainer = $true

    $countsResult = Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "exec", "-T", "db",
        "sh", "-lc",
        ('psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -f "' + $DbContainerCountSqlPath + '"')
    ) -ErrorMessage "A visszaallitott rekordszamok ellenorzese sikertelen." -CaptureOutput

    $archiveResult = Invoke-Docker -Arguments @(
        "compose", "-p", $Project,
        "exec", "-T", "backend",
        "sh", "-lc",
        'if [ -d /app/runtime/work_order_archives ]; then find /app/runtime/work_order_archives -type f | wc -l; else echo 0; fi'
    ) -ErrorMessage "Az archív fajlok szamanak ellenorzese sikertelen." -CaptureOutput

    Write-Host "Rekordszamok (users|customers|assets|work_orders|work_order_archives): $(($countsResult.Output | Out-String).Trim())"
    Write-Host "Archiv fajlok szama: $(($archiveResult.Output | Out-String).Trim())"

    $RestoreSucceeded = $true
}
catch {
    $RestoreError = $_
    Write-Error $_
}
finally {
    if ($DumpCopiedToContainer -and -not [string]::IsNullOrWhiteSpace([string]$Project)) {
        try {
            Invoke-Docker -Arguments @(
                "compose", "-p", $Project,
                "exec", "-T", "db",
                "rm", "-f", $DbContainerDumpPath
            ) -ErrorMessage "Az ideiglenes restore dump torlese sikertelen." -AllowFailure | Out-Null
        }
        catch {
            Write-Warning "Az ideiglenes restore dump nem torolheto: $($_.Exception.Message)"
        }
    }

    if (($ResetSqlCopiedToContainer -or $CountSqlCopiedToContainer) -and -not [string]::IsNullOrWhiteSpace([string]$Project)) {
        try {
            Invoke-Docker -Arguments @(
                "compose", "-p", $Project,
                "exec", "-T", "db",
                "rm", "-f", $DbContainerResetSqlPath, $DbContainerCountSqlPath
            ) -ErrorMessage "Az ideiglenes SQL fajlok torlese sikertelen." -AllowFailure | Out-Null
        }
        catch {
            Write-Warning "Az ideiglenes SQL fajlok nem torolhetok: $($_.Exception.Message)"
        }
    }

    foreach ($temporaryHostFile in @($HostResetSqlPath, $HostCountSqlPath)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$temporaryHostFile) -and (Test-Path -LiteralPath $temporaryHostFile -PathType Leaf)) {
            try {
                Remove-Item -LiteralPath $temporaryHostFile -Force
            }
            catch {
                Write-Warning "Az ideiglenes host SQL fajl nem torolheto: $temporaryHostFile"
            }
        }
    }

    Set-Location -LiteralPath $OriginalLocation
}

if (-not $RestoreSucceeded) {
    Write-Host ""
    Write-Host "A visszaallitas NEM fejezodott be sikeresen."
    if (-not [string]::IsNullOrWhiteSpace([string]$SafetyBackupDir)) {
        Write-Host "A visszaallitas elotti veszmentes itt talalhato: $SafetyBackupDir"
    }
    Write-Host "Ellenorizd az allapotot: docker compose -p $Project ps -a"
    Write-Host "Ellenorizd a naplokat: docker compose -p $Project logs --tail=200 db backend frontend"
    Write-Host "Megszakadt visszaallitas folytatasahoz hasznald a -ResumeInterruptedRestore kapcsolot."
    throw $RestoreError
}

Write-Host ""
Write-Host "A visszaallitas sikeresen befejezodott."
Write-Host "Visszaallitott mentés: $ResolvedBackupDir"
Write-Host "Compose projekt: $Project"
if (-not [string]::IsNullOrWhiteSpace([string]$SafetyBackupDir)) {
    Write-Host "Visszaallitas elotti veszmentes: $SafetyBackupDir"
}
Write-Host ""
Write-Host "Kovetkezo ellenorzesek:"
Write-Host "  docker compose -p $Project ps"
Write-Host "  docker compose -p $Project logs --tail=200 backend"
Write-Host "  Bongeszoben: Ctrl+F5, majd belepes es archiv fajl megnyitasa."
