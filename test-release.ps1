param(
    [ValidateSet("all", "unit", "pg")][string]$Suite = "all",
    [switch]$Plan,
    [string]$OutputDirectory = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Root "scripts\release_tests.py"
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
    $PythonArgs = @("-3", $Script)
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
    $PythonArgs = @($Script)
} else {
    throw "Python 3.10+ is required. Install Python, then rerun test-release.ps1."
}
$PythonArgs += @("--suite", $Suite)
if ($Plan) { $PythonArgs += "--plan" }
if ($OutputDirectory) { $PythonArgs += @("--output", $OutputDirectory) }
# PowerShell 5.1: native stderr must not become a terminating exception before
# the real process exit code is captured. Python owns timeout and cleanup.
$ErrorActionPreference = "Continue"
& $Python @PythonArgs
$Code = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($Code -ne 0) { Write-Warning "Release tests did not pass. Read test-results/<run>/report.json and the stage logs." }
exit $Code
