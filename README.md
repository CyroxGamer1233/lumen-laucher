# Lumen Launcher

Lumen is a Python/PySide6 Minecraft Java launcher with Microsoft authentication, owner-gated offline profiles, Fabric/Forge support, mod discovery, server status, skin lookup, and a Windows installer.

## Requirements

- Windows 10/11 for the .exe installer
- Python 3.11+
- Java 21 for the Fabric client-mod build
- Inno Setup 6 for local installer builds

Install Python dependencies:

~~~powershell
python -m pip install --upgrade pip
python -m pip install -e ".[gui,dev]"
~~~

## Run from source

~~~powershell
python build\gui_entry.py
~~~

The packaged GUI entry point is lumen.ui.v3.

## Authentication and offline profiles

Online Microsoft sign-in uses the device-code flow. Set the public Azure client ID only when online sign-in is needed:

~~~powershell
$env:LUMEN_MS_CLIENT_ID = "your-public-client-id"
lumen login
~~~

Offline profiles are for local single-player, LAN, and servers that explicitly permit offline profiles. The launcher unlocks offline mode after a successful ownership-verifying Microsoft sign-in on that device. Offline mode does not authenticate online-mode servers or bypass account ownership.

## Minecraft and Java installation

The launcher uses minecraft-launcher-lib to install the selected Minecraft version, loader files, and the matching Mojang Java runtime. It does not bundle or redistribute Mojang binaries.

Use the v3 UI's INSTALL MINECRAFT + JAVA action, or launch normally and let the preparation step install missing files.

## Mods, shaders, and modpacks

- Modrinth search is public and requires no API key.
- CurseForge integration is optional and requires a user-supplied CURSEFORGE_API_KEY.
- Never commit API keys, refresh tokens, or local game data.

## Build the Windows installer

From a Windows checkout:

~~~powershell
.\build\build_installer.ps1
~~~

The installer is written to:

~~~text
dist\installer\LumenSetup-<version>.exe
~~~

## GitHub Actions build

Push a version tag to build the Windows installer on a hosted Windows runner:

~~~bash
git add .
git commit -m "Release Lumen"
git push origin main
git tag v0.3.2
git push origin v0.3.2
~~~

The release workflow uploads the installer as the LumenSetup-windows artifact.

## Tests

~~~powershell
python -m compileall src tests build
python -m pytest -q
ruff check src tests
~~~

Do not commit credentials, refresh tokens, .env files, logs, local Minecraft directories, proprietary game binaries, or private API keys.
