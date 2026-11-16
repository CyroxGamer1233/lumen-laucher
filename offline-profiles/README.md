# Lumen Launcher (proof of concept)

Cross-platform Python launcher for Minecraft: Java Edition + a companion Fabric client mod.
"Lumen" is a placeholder name; do not use Feather/Mojang/Minecraft marks in your product name or logo.

## Status
| Piece | State |
|---|---|
| Core logic (settings, offline UUIDs, JVM args, checksums, signed updater, mod conflict detection, log redaction) | Implemented, unit tests passing |
| Local offline profiles (`offline_profiles.json`), network-free launch path | Implemented, covered by tests with a faked `minecraft-launcher-lib` |
| Microsoft/Xbox/Minecraft auth (device-code flow) | Implemented, **not run against live services** (needs your Azure app) |
| Install/launch via minecraft-launcher-lib | Implemented, **not run end-to-end** (needs network + Minecraft files) |
| PySide6 GUI | Offline home screen, animated page transitions, six accent themes |
| Client mod (Fabric 1.21.1 HUD, client hub, and UI accents) | Source + Gradle build; HUD widgets are movable in-game |
| Installers / signing | Templates only |

## Quick start
```
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[gui,dev]"
pytest
export LUMEN_MS_CLIENT_ID=<your Azure app id>
lumen login                    # device-code sign-in; refresh token goes to the OS keystore
lumen accounts                 # saved Microsoft accounts + offline profiles
lumen launch                   # installs Fabric + game files, checks mods, starts the game
lumen launch --account Steve   # needed when several Microsoft accounts are saved
lumen logout --account Steve
lumen mods-check
lumen settings export my-settings.json
lumen set loader_version 0.16.5   # pin the Fabric loader (`latest` to unpin)
```

## Offline / air-gapped staging mode
`--offline` (or `--profile NAME`) runs a fully local session: no Microsoft/Xbox calls, no OS keystore,
no downloads. Identities live in `offline_profiles.json` (config dir), separate from `accounts.json`.
```
lumen profile add Bench_1      # 3-16 chars: letters, digits, underscore
lumen profile list
lumen launch --profile Bench_1 # or just `lumen launch --offline` (last used profile, else settings default)
```
The game files must already be installed (one online launch, or copy a populated `minecraft/` folder
from `lumen`'s data dir). Missing files are listed and the launch stops with exit code 3.
Offline sessions use the same UUID vanilla derives (`MD5("OfflinePlayer:<name>")`, version 3), a static
32-char placeholder token and `--userType legacy`. Unlike earlier versions, offline mode does **not**
require a prior Microsoft sign-in.

Build the client mod: `cd client-mod && gradle wrapper && ./gradlew build` (JDK 21), then copy
`build/libs/lumen-client-*.jar` plus Fabric API into the instance `mods/` folder.
The instance version picker can load Mojang's full release, snapshot, and legacy version list on demand; you can also enter a custom version ID without making a network request. Install an instance before playing so its matching Java runtime is available offline. The companion Fabric client mod is currently built for Minecraft 1.21.1 only and is skipped for other game versions.
The mod adds subtle dark screen accents without a top line or button recoloring. Press **F6** in-game to open the client hub and choose **EDIT HUD LAYOUT** to drag HUD widgets; positions are saved locally.

See `docs/` for architecture, plan, security, testing and user guide.

The launcher theme selector includes Gold, Midnight Blue, Emerald, Violet, Crimson, and Arctic.
Themes change navigation and accent colors while keeping the button palette unchanged.

The offline launcher includes a saved server list with popular presets, search/online filters, and
live Minecraft status-ping details (server icon, MOTD, version, player counts, and latency). Status checks
connect directly to the entered server; the launcher does not record player visit history or
provide a directory of servers that bypass account authentication. The skin tab renders local
64×64 skins as a textured 3D-style avatar preview. Applying a skin in-game is currently supported
by the bundled Fabric client mod only on Minecraft 1.21.1. The Settings tab also has an optional
close-launcher-after-start preference; the game process continues independently.
