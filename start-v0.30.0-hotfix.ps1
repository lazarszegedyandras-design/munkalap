param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = Join-Path $ProjectRoot "compose.yaml"
$DevComposeFile = Join-Path $ProjectRoot "docker-compose.dev.yml"
$ProjectName = "munkalap"
$OriginalComposeFile = $env:COMPOSE_FILE
$OriginalAppVersion = $env:APP_VERSION
$ReleaseVersion = (Get-Content (Join-Path $ProjectRoot "VERSION") -Raw).Trim()

if (-not (Test-Path $ComposeFile)) {
    throw "Missing canonical Compose file: $ComposeFile"
}
if (-not (Test-Path $DevComposeFile)) {
    throw "Missing local development Compose override: $DevComposeFile"
}

function Assert-LocalReleaseImages {
    param([switch]$Containers)
    $Raw = & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile config --format json
    if ($LASTEXITCODE -ne 0) { throw "Could not resolve release images" }
    $Model = ($Raw | Out-String) | ConvertFrom-Json
    $Group = @("backend", "migrate", "db-role-provisioner", "runtime-permissions", "push-worker")
    $Owned = $Group + @("db", "frontend", "backup-agent", "backup-runner")
    $LockPath = Join-Path $ProjectRoot "release-images.lock.json"
    $Lock = if (Test-Path $LockPath) { Get-Content $LockPath -Raw | ConvertFrom-Json } else { $null }
    if ($Lock -and $Lock.version -ne $ReleaseVersion) { throw "Stale tested-image lock; do not deploy" }
    foreach ($Name in $Owned) {
        $Ref = $Model.services.$Name.image
        if ($Name -in $Group -and $Ref -ne $Model.services.backend.image) { throw "Mixed backend image references" }
        $RawImage = & docker image inspect $Ref
        if ($LASTEXITCODE -ne 0) { throw "Missing built release image for $Name" }
        $Image = @((($RawImage | Out-String) | ConvertFrom-Json))[0]
        if ($Image.Config.Labels.'hu.lunait.release.version' -ne $ReleaseVersion) { throw "Wrong release label for $Name" }
        if ($Lock) {
            $Kind = if ($Name -in $Group) { "backend" } else { $Name }
            if ($Lock.images.$Kind.image_id -ne $Image.Id) { throw "Image differs from tested lock: $Name. Do not rebuild after promotion." }
        }
        if ($Containers) {
            $Ids = & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile ps -aq $Name
            if ($LASTEXITCODE -ne 0 -or -not $Ids) { throw "No release container for $Name" }
            foreach ($Id in $Ids) {
                $Actual = & docker inspect --format '{{.Image}}' $Id
                if ($LASTEXITCODE -ne 0 -or $Actual.Trim() -ne $Image.Id) { throw "Stale container image for $Name" }
            }
        }
    }
    Write-Host "Release image identity check passed (production approval not implied)."
}

Write-Host "Using canonical Compose file: $ComposeFile"
Write-Host "Using local development override: $DevComposeFile"
if ($OriginalComposeFile) {
    Write-Warning "COMPOSE_FILE is set to '$OriginalComposeFile'. It is temporarily cleared by this launcher."
}

if ((Test-Path (Join-Path $ProjectRoot "release-images.lock.json")) -and -not $SkipBuild) {
    throw "A tested-image lock exists. Use -SkipBuild; rebuilding invalidates the test evidence."
}

try {
    $env:APP_VERSION = $ReleaseVersion
    Write-Host "Release: $ReleaseVersion (shared backend image)"
    Remove-Item Env:COMPOSE_FILE -ErrorAction SilentlyContinue

    $config = & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile config 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Compose validation failed; configuration is not printed because it may contain secrets."
        throw "docker compose config failed"
    }
    if (($config | Out-String) -match '(?i)\bgosu\b|\bsu-exec\b|\bsetpriv\b') {
        Write-Warning "Compose validation failed; configuration is not printed because it may contain secrets."
        throw "Unsafe/stale runtime privilege-switch command detected in effective Compose configuration."
    }

    # Stop the old project without deleting named volumes. Volume deletion is deliberately not used.
    & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile down --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw "docker compose down failed" }

    if (-not $SkipBuild) {
        & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile build backend frontend db backup-agent backup-runner
        if ($LASTEXITCODE -ne 0) { throw "docker compose build failed" }
    }

    Assert-LocalReleaseImages

    & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile up -d --no-build --force-recreate
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n--- runtime-permissions log ---"
        & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile logs --no-color --tail=100 runtime-permissions
        Write-Host "`n--- migrate log ---"
        & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile logs --no-color --tail=250 migrate
        Write-Host "`n--- db-role-provisioner log ---"
        & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile logs --no-color --tail=150 db-role-provisioner
        Write-Host "`n--- backend log ---"
        & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile logs --no-color --tail=200 backend
        throw "docker compose up failed"
    }

    Assert-LocalReleaseImages -Containers
    Write-Host "`n--- service state ---"
    & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile ps -a
    Write-Host "`nExpected fingerprints:"
    Write-Host "  runtime-permissions v0.30.0-hotfix5 ..."
    Write-Host "  migrate-entrypoint v0.30.0-hotfix4 uid=10001 gid=10001"
    Write-Host "  backend-entrypoint v0.30.0-hotfix5 uid=10001 gid=10001"
    & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile logs --no-color --tail=50 runtime-permissions migrate backend

    $LocalPort = if ($env:APP_PORT) { $env:APP_PORT } else { "3000" }
    Write-Host "`n--- local frontend access ---"
    & docker compose -p $ProjectName -f $ComposeFile -f $DevComposeFile port frontend 3000
    Write-Host "Open: http://localhost:$LocalPort"
}
finally {
    if ($null -ne $OriginalAppVersion) { $env:APP_VERSION = $OriginalAppVersion } else { Remove-Item Env:APP_VERSION -ErrorAction SilentlyContinue }
    if ($null -ne $OriginalComposeFile) {
        $env:COMPOSE_FILE = $OriginalComposeFile
    }
}
