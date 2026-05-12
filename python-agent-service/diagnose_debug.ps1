# Debug Diagnosis Script for "Debug Stopped" Error
# This script helps diagnose common debugging issues

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Debug Diagnosis for FastAPI" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$pythonExe = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$issues = @()

# 1. Check Python executable
Write-Host "[1] Checking Python executable..." -ForegroundColor Yellow
if (Test-Path $pythonExe) {
    $version = & $pythonExe --version 2>&1
    Write-Host "  ✓ Python found: $version" -ForegroundColor Green
    Write-Host "  ✓ Path: $pythonExe" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python not found at: $pythonExe" -ForegroundColor Red
    $issues += "Python executable not found"
}

# 2. Check debugpy
Write-Host "[2] Checking debugpy..." -ForegroundColor Yellow
$debugpyCheck = & $pythonExe -c "import debugpy; print(debugpy.__version__)" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ debugpy installed: $debugpyCheck" -ForegroundColor Green
} else {
    Write-Host "  ✗ debugpy not installed or error: $debugpyCheck" -ForegroundColor Red
    $issues += "debugpy not installed"
    Write-Host "  → Fix: pip install debugpy" -ForegroundColor Yellow
}

# 3. Check module import
Write-Host "[3] Checking app.main import..." -ForegroundColor Yellow
$importCheck = & $pythonExe -c "import app.main; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0 -and $importCheck -eq "OK") {
    Write-Host "  ✓ app.main can be imported" -ForegroundColor Green
} else {
    Write-Host "  ✗ app.main import failed: $importCheck" -ForegroundColor Red
    $issues += "app.main import failed"
}

# 4. Check uvicorn module
Write-Host "[4] Checking uvicorn module..." -ForegroundColor Yellow
$uvicornCheck = & $pythonExe -c "import uvicorn; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0 -and $uvicornCheck -eq "OK") {
    Write-Host "  ✓ uvicorn can be imported" -ForegroundColor Green
} else {
    Write-Host "  ✗ uvicorn import failed: $uvicornCheck" -ForegroundColor Red
    $issues += "uvicorn not installed"
    Write-Host "  → Fix: pip install uvicorn" -ForegroundColor Yellow
}

# 5. Test uvicorn command
Write-Host "[5] Testing uvicorn command..." -ForegroundColor Yellow
$uvicornTest = & $pythonExe -m uvicorn --help 2>&1 | Select-Object -First 1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ uvicorn command works" -ForegroundColor Green
} else {
    Write-Host "  ✗ uvicorn command failed" -ForegroundColor Red
    $issues += "uvicorn command failed"
}

# 6. Check .env file
Write-Host "[6] Checking .env file..." -ForegroundColor Yellow
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Write-Host "  ✓ .env file exists" -ForegroundColor Green
} else {
    Write-Host "  ⚠ .env file not found (optional, but recommended)" -ForegroundColor Yellow
}

# 7. Check launch.json path
Write-Host "[7] Checking launch.json configuration..." -ForegroundColor Yellow
$launchJson = Join-Path (Split-Path $PSScriptRoot -Parent) ".vscode\launch.json"
if (Test-Path $launchJson) {
    $content = Get-Content $launchJson -Raw
    if ($content -match "python-agent-service/venv/Scripts/python.exe") {
        Write-Host "  ✓ launch.json has correct Python path" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ launch.json Python path may be incorrect" -ForegroundColor Yellow
        $issues += "launch.json Python path issue"
    }
} else {
    Write-Host "  ✗ launch.json not found" -ForegroundColor Red
    $issues += "launch.json not found"
}

# 8. Check VS Code Python extension
Write-Host "[8] Recommendations..." -ForegroundColor Yellow
Write-Host "  → Make sure Python extension is installed in VS Code/Cursor" -ForegroundColor Cyan
Write-Host "  → Press Ctrl+Shift+P, type 'Python: Select Interpreter'" -ForegroundColor Cyan
Write-Host "  → Select: python-agent-service/venv/Scripts/python.exe" -ForegroundColor Cyan
Write-Host "  → Try 'Python: FastAPI (No Reload)' config if reload causes issues" -ForegroundColor Cyan

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($issues.Count -eq 0) {
    Write-Host "✓ No obvious issues found!" -ForegroundColor Green
    Write-Host ""
    Write-Host "If debug still fails, try:" -ForegroundColor Yellow
    Write-Host "  1. Restart VS Code/Cursor" -ForegroundColor White
    Write-Host "  2. Select Python interpreter manually (Ctrl+Shift+P)" -ForegroundColor White
    Write-Host "  3. Check debug console for error messages" -ForegroundColor White
    Write-Host "  4. Try 'Python: FastAPI (No Reload)' configuration" -ForegroundColor White
} else {
    Write-Host "✗ Found $($issues.Count) issue(s):" -ForegroundColor Red
    foreach ($issue in $issues) {
        Write-Host "  - $issue" -ForegroundColor Red
    }
}
