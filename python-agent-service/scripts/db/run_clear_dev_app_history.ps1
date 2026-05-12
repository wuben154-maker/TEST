#Requires -Version 5.1
<#
.SYNOPSIS
  Clears dev app history via Python (see run_clear_dev_app_history.py).

.DESCRIPTION
  Run from repo root or any cwd. Does not override DATABASE_URL unless set in the shell.
#>
$ErrorActionPreference = "Stop"

$serviceRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$venvPy = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$py = $null
if (Test-Path $venvPy) { $py = $venvPy }
else {
  $cmdPy = Get-Command python -ErrorAction SilentlyContinue
  if ($cmdPy) { $py = $cmdPy.Source }
}
if (-not $py) {
  throw "python not found. Create python-agent-service\.venv or install Python."
}

$runner = Join-Path $PSScriptRoot "run_clear_dev_app_history.py"
Write-Host "Running: $py $runner"
& $py $runner
exit $LASTEXITCODE
