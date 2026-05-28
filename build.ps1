$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name DragCalculator `
    --paths src `
    --collect-all rapidocr_onnxruntime `
    .\run.py

Write-Host "Built dist\DragCalculator\DragCalculator.exe"

