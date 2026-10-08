[CmdletBinding()]
param(
    [switch]$DownloadModel,
    [switch]$ResetTestDatabase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectName = 'sionggpt-integration-gate'
$testVolumeName = 'sionggpt_test_pgdata_phase45'
$testContainerName = 'sionggpt-test-postgres'
$testDatabaseName = 'sionggpt_test'
$migrationDatabaseName = 'sionggpt_migration_test'
$testDatabaseUser = 'sionggpt_test_user'
$testHost = '127.0.0.1'
$testPort = 55432
$modelRevision = 'fd1525a9fd15316a2d503bf26ab031a61d056e98'
$modelTarget = 'C:\siongGPT-data\models\multilingual-e5-small-fd1525'
$healthTimeoutSeconds = 120

$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path (Join-Path $backendRoot '..')).Path
$composeFile = Join-Path $repositoryRoot 'infra\docker-compose.test.yml'
$environmentExample = Join-Path $backendRoot '.env.integration.example'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$modelScript = Join-Path $backendRoot 'scripts\prepare_embedding_model.py'
$gateScript = Join-Path $backendRoot 'scripts\run_integration_gate.py'

$previousDockerContext = $env:DOCKER_CONTEXT
$previousBaselineDatabaseUrl = $env:BASELINE_DEVELOPMENT_DATABASE_URL
$previousTestDatabaseUrl = $env:TEST_DATABASE_URL
$previousMigrationDatabaseUrl = $env:TEST_MIGRATION_DATABASE_URL
$previousDestructiveFlag = $env:ALLOW_DESTRUCTIVE_DB_TESTS
$previousTestDatabasePassword = $env:SIONGGPT_TEST_DB_PASSWORD
$previousModelPath = $env:EMBEDDING_MODEL_LOCAL_PATH
$previousDownloadFlag = $env:EMBEDDING_ALLOW_DOWNLOAD
$composeStarted = $false
$gateExitCode = 2
$testPassword = $null
$encodedPassword = $null
$baselineDevelopmentDatabaseUrl = $null

function Invoke-TestCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose --project-name $projectName --file $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "The isolated Phase 4.5 Compose command failed with exit code $LASTEXITCODE."
    }
}

function Assert-RepositoryContract {
    foreach ($requiredPath in @($composeFile, $environmentExample, $python, $modelScript, $gateScript)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Required Phase 4.5 file is missing: $requiredPath"
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $backendRoot 'app\main.py') -PathType Leaf)) {
        throw 'The script is not located in the expected SiongGPT repository.'
    }

    $composeText = Get-Content -LiteralPath $composeFile -Raw
    $environmentText = Get-Content -LiteralPath $environmentExample -Raw
    foreach ($name in @('SIONGGPT_TEST_DB_PASSWORD', 'TEST_DATABASE_URL', 'TEST_MIGRATION_DATABASE_URL', 'ALLOW_DESTRUCTIVE_DB_TESTS', 'EMBEDDING_MODEL_LOCAL_PATH', 'EMBEDDING_ALLOW_DOWNLOAD')) {
        if ($environmentText -notmatch "(?m)^$([regex]::Escape($name))=") {
            throw "The integration environment contract is missing $name."
        }
    }
    foreach ($expected in @(
        'name: sionggpt-integration-gate',
        '127.0.0.1:55432:5432',
        'sionggpt_test_pgdata_phase45',
        'POSTGRES_DB: sionggpt_test',
        'POSTGRES_USER: sionggpt_test_user'
    )) {
        if (-not $composeText.Contains($expected)) {
            throw "The isolated Compose contract does not contain the expected value: $expected"
        }
    }
    if ($composeText -match '(?m)^\s*-?\s*postgres_data\s*:') {
        throw 'The Phase 4.5 Compose file must not reuse the development postgres_data volume.'
    }
}

function Assert-DockerServer {
    $rawVersion = & docker version --format '{{json .}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $rawVersion) {
        throw 'Docker Server is unavailable. Run this script from the user PowerShell that can access Docker Desktop.'
    }
    try {
        $version = $rawVersion | ConvertFrom-Json
    }
    catch {
        throw 'Docker version output could not be validated.'
    }
    if (-not $version.Client.Version -or -not $version.Server.Version) {
        throw 'Both Docker Client and Server are required; stopping before any test resource is changed.'
    }
    Write-Host "Docker Client $($version.Client.Version) and Server $($version.Server.Version) are available."
}

function New-TestPassword {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

function Get-BaselineDevelopmentDatabaseUrl {
    if ($env:BASELINE_DEVELOPMENT_DATABASE_URL) {
        return $env:BASELINE_DEVELOPMENT_DATABASE_URL
    }
    Push-Location $backendRoot
    try {
        $captured = & $python -c "from app.core.config import settings; print(settings.database_url)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $captured) {
            throw 'Could not load the baseline development database identity through application Settings.'
        }
        return ($captured | Select-Object -Last 1).Trim()
    }
    finally {
        Pop-Location
    }
}

function Reset-ExactTestVolume {
    if ($projectName -ne 'sionggpt-integration-gate' -or
        $testVolumeName -ne 'sionggpt_test_pgdata_phase45' -or
        $testDatabaseName -notmatch '(^|_)test($|_)' -or
        $migrationDatabaseName -notmatch '(^|_)test($|_)') {
        throw 'Refusing reset because the exact Phase 4.5 test identity check failed.'
    }

    Invoke-TestCompose down
    $existing = & docker volume inspect $testVolumeName 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'The exact Phase 4.5 test volume does not exist; a fresh one will be created.'
        return
    }
    $volume = ($existing | ConvertFrom-Json)[0]
    if ($volume.Name -ne $testVolumeName -or
        $volume.Labels.'com.docker.compose.project' -ne $projectName -or
        $volume.Labels.'com.docker.compose.volume' -ne 'sionggpt_test_pgdata') {
        throw 'Refusing to delete a volume whose exact Compose identity does not match Phase 4.5.'
    }
    & docker volume rm $testVolumeName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'The exact Phase 4.5 test volume could not be removed.'
    }
    Write-Host 'Removed only the explicitly authorized Phase 4.5 test volume.'
}

function Wait-TestPostgresHealthy {
    $deadline = [DateTime]::UtcNow.AddSeconds($healthTimeoutSeconds)
    do {
        $status = & docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' $testContainerName 2>$null
        if ($LASTEXITCODE -eq 0 -and $status -eq 'healthy') {
            Write-Host 'Isolated PostgreSQL/pgvector test container is healthy.'
            return
        }
        if ($status -eq 'unhealthy') {
            throw 'The isolated PostgreSQL test container became unhealthy.'
        }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out after $healthTimeoutSeconds seconds waiting for the isolated PostgreSQL healthcheck."
}

function Initialize-RunDatabases {
    if ($testPassword -notmatch '^[0-9a-f]{64}$' -or
        $testDatabaseName -notmatch '^sionggpt_test_[0-9a-f]{12}$' -or
        $migrationDatabaseName -notmatch '^sionggpt_migration_test_[0-9a-f]{12}$') {
        throw 'Refusing database initialization because generated test identities are invalid.'
    }
    $setupSql = @"
ALTER ROLE $testDatabaseUser PASSWORD '$testPassword';
CREATE DATABASE $testDatabaseName OWNER $testDatabaseUser;
CREATE DATABASE $migrationDatabaseName OWNER $testDatabaseUser;
"@
    $setupSql | & docker exec --interactive $testContainerName psql `
        --username $testDatabaseUser --dbname postgres --no-psqlrc `
        --set ON_ERROR_STOP=1 --quiet
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not initialize the two fresh per-run Phase 4.5 test databases.'
    }
    $setupSql = $null
    Write-Host 'Created two fresh isolated databases for this Gate run.'
}

try {
    Assert-RepositoryContract
    $env:DOCKER_CONTEXT = 'desktop-linux'
    Assert-DockerServer

    $baselineDevelopmentDatabaseUrl = Get-BaselineDevelopmentDatabaseUrl
    $env:BASELINE_DEVELOPMENT_DATABASE_URL = $baselineDevelopmentDatabaseUrl

    $testPassword = New-TestPassword
    $runSuffix = $testPassword.Substring(0, 12)
    $testDatabaseName = "sionggpt_test_$runSuffix"
    $migrationDatabaseName = "sionggpt_migration_test_$runSuffix"
    $encodedPassword = [Uri]::EscapeDataString($testPassword)
    $env:SIONGGPT_TEST_DB_PASSWORD = $testPassword
    $env:TEST_DATABASE_URL = "postgresql+psycopg://${testDatabaseUser}:${encodedPassword}@${testHost}:${testPort}/${testDatabaseName}"
    $env:TEST_MIGRATION_DATABASE_URL = "postgresql+psycopg://${testDatabaseUser}:${encodedPassword}@${testHost}:${testPort}/${migrationDatabaseName}"
    $env:ALLOW_DESTRUCTIVE_DB_TESTS = 'true'
    $env:EMBEDDING_MODEL_LOCAL_PATH = $modelTarget
    $env:EMBEDDING_ALLOW_DOWNLOAD = 'false'

    if ($ResetTestDatabase) {
        Reset-ExactTestVolume
    }

    Invoke-TestCompose up -d
    $composeStarted = $true
    Wait-TestPostgresHealthy
    Initialize-RunDatabases

    & $python $modelScript --help | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not verify the pinned model preparation script interface.'
    }
    if (Test-Path -LiteralPath $modelTarget -PathType Container) {
        & $python $modelScript --target $modelTarget
    }
    elseif ($DownloadModel) {
        $modelParent = Split-Path -Parent $modelTarget
        New-Item -ItemType Directory -Force -Path $modelParent | Out-Null
        & $python $modelScript --target $modelTarget --download
    }
    else {
        throw "Pinned model is absent. Re-run with -DownloadModel to fetch the fixed approved revision $modelRevision."
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'Pinned model preparation or manifest validation failed. Resolve the reported model issue and retry.'
    }

    Push-Location $backendRoot
    try {
        & $python $gateScript
        $gateExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($gateExitCode -eq 0) {
        Write-Host 'Phase 4.5 Gate Runner completed successfully.'
    }
    else {
        Write-Error "Phase 4.5 Gate Runner failed with exit code $gateExitCode. Review its redacted check results; do not start Phase 5."
    }
}
catch {
    if ($gateExitCode -eq 0) {
        $gateExitCode = 2
    }
    Write-Error $_.Exception.Message
}
finally {
    if ($composeStarted) {
        try {
            & docker compose --project-name $projectName --file $composeFile stop | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Warning 'Could not stop the isolated Phase 4.5 Compose project; stop that exact project manually.'
            }
        }
        catch {
            Write-Warning 'Could not stop the isolated Phase 4.5 Compose project; stop that exact project manually.'
        }
    }

    $env:DOCKER_CONTEXT = $previousDockerContext
    $env:BASELINE_DEVELOPMENT_DATABASE_URL = $previousBaselineDatabaseUrl
    $env:TEST_DATABASE_URL = $previousTestDatabaseUrl
    $env:TEST_MIGRATION_DATABASE_URL = $previousMigrationDatabaseUrl
    $env:ALLOW_DESTRUCTIVE_DB_TESTS = $previousDestructiveFlag
    $env:SIONGGPT_TEST_DB_PASSWORD = $previousTestDatabasePassword
    $env:EMBEDDING_MODEL_LOCAL_PATH = $previousModelPath
    $env:EMBEDDING_ALLOW_DOWNLOAD = $previousDownloadFlag
    $testPassword = $null
    $encodedPassword = $null
    $baselineDevelopmentDatabaseUrl = $null
}

exit $gateExitCode
