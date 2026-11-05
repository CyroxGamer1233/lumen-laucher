# Windows: build mod, run tests, build bundle, then installer (Inno Setup 6 required).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pip install -e ".[gui,dev]"
python -m pytest -q
Push-Location client-mod; .\gradlew.bat --no-daemon build; Pop-Location
python build\build_launcher.py
& "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe" build\installer.iss
