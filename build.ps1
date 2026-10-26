# Builds a standalone dist\Pixelfront.exe (no Python needed on the target machine).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Pixelfront main.py

Write-Host "Built dist\Pixelfront.exe"
