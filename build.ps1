param([string]$Python = '.\.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name MySeriesList --icon 'static/branding/series-watchlist.ico' --add-data 'templates;templates' --add-data 'static;static' run_desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'MySeriesList build failed.' }
} finally { Pop-Location }
