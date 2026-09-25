[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProjectRoot = (Get-Location).Path,

    [Parameter()]
    [string]$OutputRoot = ".\backups",

    [Parameter()]
    [switch]$IncludeContainerExports
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-DockerSuccess {
    param([Parameter(Mandatory)][string]$Message)

    if ($LASTEXITCODE -ne 0) {
        throw "$Message (Docker hibakod: $LASTEXITCODE)"
    }
}

function Get-RequiredContainerId {
    param(
        [Parameter(Mandatory)][string]$Service,
        [switch]$IncludeStopped
    )

    # Ne csovezzuk a natív Docker-kimenetet Select-Object -First 1-be.
    # PowerShell ilyenkor idö elött lezarhatja a pipe-ot, amitöl a Docker
    # hibasan -1 exit koddal terhet vissza, miközben a kontener valojaban letezik.
    if ($IncludeStopped) {
        $composeOutput = @(docker compose ps -a -q $Service 2>&1)
    }
    else {
        $composeOutput = @(docker compose ps -q $Service 2>&1)
    }
    $composeExitCode = $LASTEXITCODE

    if ($composeExitCode -ne 0) {
        $details = ($composeOutput | Out-String).Trim()
        throw "A(z) '$Service' kontener azonositojanak lekerdezese sikertelen. Docker hibakod: $composeExitCode. $details"
    }

    $containerIds = @(
        $composeOutput |
            ForEach-Object { [string]$_ } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )

    if ($containerIds.Count -eq 0) {
        $statusOutput = @(docker compose ps -a 2>&1)
        $statusText = ($statusOutput | Out-String).Trim()
        throw "A(z) '$Service' kontener nem talalhato. A projekt gyokerkonyvtarabol futtasd a scriptet. Compose allapot:`n$statusText"
    }

    return $containerIds[0].Trim()
}

function Remove-ContainerIfExists {
    param([Parameter(Mandatory)][string]$ContainerName)

    $names = @(docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}" 2>$null)
    $lookupExitCode = $LASTEXITCODE

    if ($lookupExitCode -ne 0) {
        Write-Warning "Az ideiglenes kontener lekerdezese sikertelen: $ContainerName"
        return
    }

    if (@($names | Where-Object { ([string]$_).Trim() -eq $ContainerName }).Count -gt 0) {
        docker rm -f $ContainerName 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Az ideiglenes kontener nem torolheto: $ContainerName"
        }
    }
}

function Get-ContainerInspect {
    param([Parameter(Mandatory)][string]$ContainerId)

    $inspect = docker inspect $ContainerId | ConvertFrom-Json
    Assert-DockerSuccess "A kontener vizsgalata sikertelen: $ContainerId"

    if ($null -eq $inspect -or $inspect.Count -eq 0) {
        throw "Ures docker inspect valasz: $ContainerId"
    }

    return $inspect[0]
}

function Assert-NonEmptyFile {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "A mentett fajl nem talalhato: $Path"
    }

    if ((Get-Item -LiteralPath $Path).Length -le 0) {
        throw "A mentett fajl ures: $Path"
    }
}

$OriginalLocation = (Get-Location).Path
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ContainerDumpPath = "/tmp/munkalap-database-$Stamp.dump"
$RuntimeTempContainer = "munkalap-runtime-backup-$Stamp"
$BackendWasRunning = $false
$FrontendWasRunning = $false
$ApplicationStopped = $false
$RuntimeTempCreated = $false
$BackupCompleted = $false
$DbContainer = $null

try {
    Set-Location -LiteralPath $ProjectRoot

    foreach ($requiredFile in @("docker-compose.yml", ".env", "VERSION")) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Hianyzik a projektfajl: $requiredFile. ProjectRoot: $ProjectRoot"
        }
    }

    docker compose config --quiet
    Assert-DockerSuccess "A Docker Compose konfiguracio ervenytelen."

    if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
        $OutputRootAbsolute = [System.IO.Path]::GetFullPath($OutputRoot)
    }
    else {
        $OutputRootAbsolute = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $OutputRoot))
    }
    $BackupDir = Join-Path $OutputRootAbsolute "backup-$Stamp"
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

    $DbDumpPath = Join-Path $BackupDir "database-$Stamp.dump"
    $RuntimeBackupPath = Join-Path $BackupDir "app-runtime-$Stamp.tar.gz"
    $ImageSavePath = Join-Path $BackupDir "docker-images-$Stamp.tar"
    $ManifestPath = Join-Path $BackupDir "manifest.json"
    $ChecksumPath = Join-Path $BackupDir "checksums.sha256"

    $DbContainer = Get-RequiredContainerId -Service "db"
    $BackendContainer = Get-RequiredContainerId -Service "backend" -IncludeStopped
    $FrontendContainer = Get-RequiredContainerId -Service "frontend" -IncludeStopped

    $DbInspect = Get-ContainerInspect -ContainerId $DbContainer
    $BackendInspect = Get-ContainerInspect -ContainerId $BackendContainer
    $FrontendInspect = Get-ContainerInspect -ContainerId $FrontendContainer

    if (-not $DbInspect.State.Running) {
        throw "A db kontener nem fut; pg_dump nem keszitheto."
    }

    $BackendWasRunning = [bool]$BackendInspect.State.Running
    $FrontendWasRunning = [bool]$FrontendInspect.State.Running

    $ComposeProject = $DbInspect.Config.Labels.'com.docker.compose.project'
    if ([string]::IsNullOrWhiteSpace($ComposeProject)) {
        throw "A Docker Compose projektneve nem hatarozhato meg."
    }

    $DbVolume = @($DbInspect.Mounts | Where-Object { $_.Destination -eq "/var/lib/postgresql/data" })[0].Name
    $RuntimeVolume = @($BackendInspect.Mounts | Where-Object { $_.Destination -eq "/app/runtime" })[0].Name

    if ([string]::IsNullOrWhiteSpace($DbVolume)) {
        throw "A postgres_data volume nem azonosithato a /var/lib/postgresql/data csatolason."
    }

    if ([string]::IsNullOrWhiteSpace($RuntimeVolume)) {
        throw "Az app_runtime volume nem azonosithato a /app/runtime csatolason."
    }

    $DbImageRef = [string]$DbInspect.Config.Image
    $BackendImageRef = [string]$BackendInspect.Config.Image
    $FrontendImageRef = [string]$FrontendInspect.Config.Image

    Write-Host "Mentési konyvtar: $BackupDir"
    Write-Host "Compose projekt: $ComposeProject"
    Write-Host "Adatbazis volume: $DbVolume"
    Write-Host "Runtime volume: $RuntimeVolume"
    Write-Host ""

    Write-Host "1/7 Telepitesi konfiguracio mentese..."
    Copy-Item -LiteralPath ".env" -Destination (Join-Path $BackupDir ".env") -Force
    Copy-Item -LiteralPath "docker-compose.yml" -Destination (Join-Path $BackupDir "docker-compose.yml") -Force
    Copy-Item -LiteralPath "VERSION" -Destination (Join-Path $BackupDir "VERSION") -Force
    if (Test-Path -LiteralPath "CHANGELOG.md") {
        Copy-Item -LiteralPath "CHANGELOG.md" -Destination (Join-Path $BackupDir "CHANGELOG.md") -Force
    }

    docker compose config | Set-Content -LiteralPath (Join-Path $BackupDir "compose-effective.yml") -Encoding UTF8
    Assert-DockerSuccess "Az effektív Compose konfiguracio mentese sikertelen."

    docker version | Set-Content -LiteralPath (Join-Path $BackupDir "docker-version.txt") -Encoding UTF8
    Assert-DockerSuccess "A Docker verzio lekerdezese sikertelen."

    docker compose version | Set-Content -LiteralPath (Join-Path $BackupDir "docker-compose-version.txt") -Encoding UTF8
    Assert-DockerSuccess "A Docker Compose verzio lekerdezese sikertelen."

    Write-Host "2/7 Alkalmazas irasvedett allapotba helyezese..."
    if ($FrontendWasRunning -or $BackendWasRunning) {
        $servicesToStop = @()
        if ($FrontendWasRunning) { $servicesToStop += "frontend" }
        if ($BackendWasRunning) { $servicesToStop += "backend" }

        docker compose stop @servicesToStop
        Assert-DockerSuccess "A frontend/backend leallitasa sikertelen."
        $ApplicationStopped = $true
    }

    Write-Host "3/7 PostgreSQL custom dump keszitese es ellenorzese..."
    $dumpCommand = 'rm -f "' + $ContainerDumpPath + '" && pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "' + $ContainerDumpPath + '"'
    docker compose exec -T db sh -lc $dumpCommand
    Assert-DockerSuccess "A PostgreSQL pg_dump sikertelen."

    $verifyDumpCommand = 'pg_restore --list "' + $ContainerDumpPath + '" >/dev/null'
    docker compose exec -T db sh -lc $verifyDumpCommand
    Assert-DockerSuccess "A PostgreSQL dump belso ellenorzese sikertelen."

    docker compose cp "db:$ContainerDumpPath" $DbDumpPath
    Assert-DockerSuccess "A PostgreSQL dump kimásolasa sikertelen."
    Assert-NonEmptyFile -Path $DbDumpPath

    Write-Host "4/7 app_runtime volume mentese..."
    Remove-ContainerIfExists -ContainerName $RuntimeTempContainer

    $runtimeCommand = 'cd /app/runtime && tar -czf /tmp/app-runtime.tar.gz . && tar -tzf /tmp/app-runtime.tar.gz >/dev/null'
    docker compose run -T --name $RuntimeTempContainer --no-deps --entrypoint sh backend -lc $runtimeCommand
    Assert-DockerSuccess "Az app_runtime volume TAR-mentese sikertelen."
    $RuntimeTempCreated = $true

    docker cp "${RuntimeTempContainer}:/tmp/app-runtime.tar.gz" $RuntimeBackupPath
    Assert-DockerSuccess "Az app_runtime TAR kimásolasa sikertelen."
    Assert-NonEmptyFile -Path $RuntimeBackupPath

    Write-Host "5/7 PostgreSQL, backend es frontend image-ek mentese..."
    docker image save --output $ImageSavePath $DbImageRef $BackendImageRef $FrontendImageRef
    Assert-DockerSuccess "A Docker image-ek mentese sikertelen."
    Assert-NonEmptyFile -Path $ImageSavePath

    if ($IncludeContainerExports) {
        Write-Host "6/7 Opcionális kontener-fajlrendszer exportok..."
        foreach ($item in @(
            @{ Name = "db"; Id = $DbContainer },
            @{ Name = "backend"; Id = $BackendContainer },
            @{ Name = "frontend"; Id = $FrontendContainer }
        )) {
            $exportPath = Join-Path $BackupDir ("container-{0}-{1}.tar" -f $item.Name, $Stamp)
            docker container export --output $exportPath $item.Id
            Assert-DockerSuccess "A(z) $($item.Name) kontener exportja sikertelen."
            Assert-NonEmptyFile -Path $exportPath
        }
    }
    else {
        Write-Host "6/7 Kontenerexport kihagyva (helyesen: a volume-okat nem mentene)."
    }

    Write-Host "7/7 Manifest es SHA-256 ellenorzoosszegek..."
    $Manifest = [ordered]@{
        format = "munkalap-app-host-backup"
        format_version = 1
        created_at = (Get-Date).ToString("o")
        application_version = (Get-Content -LiteralPath "VERSION" -Raw).Trim()
        compose_project = $ComposeProject
        consistency = "frontend/backend stopped; database and runtime captured while application writes were disabled"
        services = [ordered]@{
            db = [ordered]@{
                container_id = $DbContainer
                image = $DbImageRef
                volume = $DbVolume
            }
            backend = [ordered]@{
                container_id = $BackendContainer
                image = $BackendImageRef
                runtime_volume = $RuntimeVolume
            }
            frontend = [ordered]@{
                container_id = $FrontendContainer
                image = $FrontendImageRef
            }
        }
        files = [ordered]@{
            database_dump = [System.IO.Path]::GetFileName($DbDumpPath)
            app_runtime = [System.IO.Path]::GetFileName($RuntimeBackupPath)
            docker_images = [System.IO.Path]::GetFileName($ImageSavePath)
            compose = "docker-compose.yml"
            environment = ".env"
            effective_compose = "compose-effective.yml"
        }
        warnings = @(
            ".env and compose-effective.yml may contain secrets; protect the backup directory.",
            "Container exports, when enabled, do not contain Docker volume data.",
            "A backup is only proven after a test restore."
        )
    }

    $Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

    $filesToHash = Get-ChildItem -LiteralPath $BackupDir -File | Where-Object { $_.Name -ne "checksums.sha256" }
    $checksumLines = foreach ($file in $filesToHash) {
        $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
        "{0} *{1}" -f $hash.Hash.ToLowerInvariant(), $file.Name
    }
    $checksumLines | Set-Content -LiteralPath $ChecksumPath -Encoding ASCII

    $BackupCompleted = $true
}
finally {
    try {
        if (
            -not [string]::IsNullOrWhiteSpace([string]$DbContainer) -and
            -not [string]::IsNullOrWhiteSpace($ContainerDumpPath)
        ) {
            docker compose exec -T db rm -f $ContainerDumpPath 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Az ideiglenes PostgreSQL dump nem torolheto a db kontenerbol."
            }
        }
    }
    catch {
        Write-Warning "Az ideiglenes PostgreSQL dump nem torolheto a db kontenerbol: $($_.Exception.Message)"
    }

    try {
        Remove-ContainerIfExists -ContainerName $RuntimeTempContainer
    }
    catch {
        Write-Warning "Az ideiglenes runtime-mento kontener ellenorzese vagy torlese sikertelen: $($_.Exception.Message)"
    }

    if ($ApplicationStopped) {
        try {
            $servicesToStart = @()
            if ($BackendWasRunning) { $servicesToStart += "backend" }
            if ($FrontendWasRunning) { $servicesToStart += "frontend" }

            if ($servicesToStart.Count -gt 0) {
                docker compose start @servicesToStart | Out-Host
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "A frontend/backend automatikus ujrainditasa sikertelen. Futtasd: docker compose start backend frontend"
                }
            }
        }
        catch {
            Write-Warning "Az alkalmazas automatikus ujrainditasa sikertelen: $($_.Exception.Message)"
        }
    }

    Set-Location -LiteralPath $OriginalLocation
}

if (-not $BackupCompleted) {
    throw "A mentés nem fejezodott be sikeresen."
}

Write-Host ""
Write-Host "A teljes host-oldali mentés elkészült: $BackupDir"
Write-Host ""
Get-ChildItem -LiteralPath $BackupDir -File |
    Sort-Object Name |
    Select-Object Name, Length, LastWriteTime |
    Format-Table -AutoSize
Write-Host ""
Write-Host "FONTOS: masold a backup konyvtarat masik fizikai meghajtora vagy NAS-ra, es vegezz probavisszaallitast."
