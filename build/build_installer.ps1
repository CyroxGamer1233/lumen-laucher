# Build the Windows installer for Lumen.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install -e ".[gui,dev]"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

if (Get-Command gradle -ErrorAction SilentlyContinue) {
    Push-Location client-mod
    gradle --no-daemon build
    if ($LASTEXITCODE -ne 0) { throw "Client mod build failed." }
    Pop-Location
} else {
    Write-Warning "Gradle was not found; continuing without rebuilding the optional client mod."
}

python build\build_launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$iscc = Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"
if (-not (Test-Path -LiteralPath $iscc)) {
    throw "Install Inno Setup 6 before building the installer."
}

$version = "0.3.2"
& $iscc "/DAppVersion=$version" build\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

Write-Host "Installer ready: dist\installer\LumenSetup-$version.exe"
