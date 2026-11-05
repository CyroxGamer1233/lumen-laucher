# Lumen Launcher (proof of concept)

Cross-platform Python launcher for Minecraft: Java Edition + a companion Fabric client mod.
"Lumen" is a placeholder name; do not use Feather/Mojang/Minecraft marks in your product name or logo.

## Status
| Piece | State |
|---|---|
| Core logic (settings, offline UUIDs, JVM args, checksums, signed updater, mod conflict detection, log redaction) | Implemented, 12 unit tests passing |
| Microsoft/Xbox/Minecraft auth (device-code flow) | Implemented, **not run against live services** (needs your Azure app) |
| Install/launch via minecraft-launcher-lib | Implemented, **not run end-to-end** (needs network + Minecraft files) |
| PySide6 GUI | Minimal skeleton, **untested** |
| Client mod (Fabric 1.21.1 HUD + benchmark recorder) | Source + Gradle build, **not compiled yet** |
| Installers / signing | Templates only |

## Quick start
```
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[gui,dev]"
pytest
export LUMEN_MS_CLIENT_ID=<your Azure app id>
lumen login            # device-code sign-in; refresh token goes to the OS keystore
lumen launch           # installs Fabric + game files, checks mods, starts the game
lumen launch --offline # only after a successful login on this device
lumen mods-check
lumen settings export my-settings.json
```
Build the client mod: `cd client-mod && gradle wrapper && ./gradlew build` (JDK 21), then copy
`build/libs/lumen-client-*.jar` plus Fabric API into the instance `mods/` folder.

See `docs/` for architecture, plan, security, testing and user guide.
