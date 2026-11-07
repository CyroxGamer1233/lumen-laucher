$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -e ".[gui,dev]"
python -m pytest -q

Remove-Item -Recurse -Force dist, build/pyinstaller -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --windowed --name LumenOffline --paths src --collect-all PySide6 gui_entry.py

& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (Join-Path $PSScriptRoot "installer.iss")
Write-Host "Installer created in $PWD\dist"
