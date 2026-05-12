# Environment Check Script
# Checks if virtual environment is properly set up

Write-Host "=== Python Environment Check ===" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "1. Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "   $pythonVersion" -ForegroundColor Green

# Check Python path
Write-Host "`n2. Checking Python executable path..." -ForegroundColor Yellow
$pythonPath = python -c "import sys; print(sys.executable)" 2>&1
Write-Host "   $pythonPath" -ForegroundColor Green

# Check if using venv
$isVenv = $pythonPath -like "*venv*"
if ($isVenv) {
    Write-Host "   ✓ Using virtual environment" -ForegroundColor Green
} else {
    Write-Host "   ✗ NOT using virtual environment!" -ForegroundColor Red
    Write-Host "   Please activate virtual environment:" -ForegroundColor Yellow
    Write-Host "   .\activate.ps1" -ForegroundColor Cyan
}

# Check structlog
Write-Host "`n3. Checking structlog module..." -ForegroundColor Yellow
try {
    $structlogVersion = python -c "import structlog; print(structlog.__version__)" 2>&1
    Write-Host "   ✓ structlog $structlogVersion installed" -ForegroundColor Green
} catch {
    Write-Host "   ✗ structlog not found!" -ForegroundColor Red
    Write-Host "   Installing structlog..." -ForegroundColor Yellow
    python -m pip install structlog>=24.4.0
}

# Check other key modules
Write-Host "`n4. Checking other key modules..." -ForegroundColor Yellow
$modules = @("langchain", "fastapi", "pydantic")
foreach ($module in $modules) {
    try {
        python -c "import $module" 2>&1 | Out-Null
        Write-Host "   ✓ $module" -ForegroundColor Green
    } catch {
        Write-Host "   ✗ $module not found" -ForegroundColor Red
    }
}

Write-Host "`n=== Check Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "If modules are missing, run:" -ForegroundColor Yellow
Write-Host "  pip install -r requirements.txt" -ForegroundColor Cyan
