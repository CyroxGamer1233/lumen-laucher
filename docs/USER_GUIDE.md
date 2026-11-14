# User guide

## Sign in
1. Run `lumen login`. A code and a Microsoft URL are shown; open the URL and enter the code.
2. After a successful sign-in the launcher remembers you via your operating system's secure keystore. You can sign out any time to remove it.

You need a Minecraft: Java Edition account (Game Pass for PC works if it shows a Java profile).

## Play
- Choose a Minecraft version and loader (Fabric recommended) and press Play. First start downloads about 1 GB.
- **Offline profile**: available after one successful sign-in on this device. Offline play works for single-player/LAN and servers that permit it; most public servers require a real account.
- Offline play works for single-player/LAN and servers that permit it; most public servers require a real account.

## Mods
- Put Fabric mods in the instance `mods/` folder or install from Modrinth.
- `lumen mods-check` lists missing dependencies, version mismatches, duplicates and known conflicts. The launcher refuses to start on errors unless you pass `--force`.
- The "performance" profile suggests Sodium, Lithium, FerriteCore, ModernFix, ImmediatelyFast and Entity Culling.

## Performance tips
- Memory: the launcher picks a heap automatically (about a third of RAM, capped). More is not always faster.
- Profiles: low_end (small heap), balanced, high_end (pre-touched heap, longer start, steadier frames).
- In game: **F6** opens the Lumen Client Hub; **F7** toggles the HUD. The mod adds subtle dark-and-gold screen accents without recoloring Minecraft buttons. The hub controls FPS/CPS, keystrokes, armor and potion overlays, plus low-end and balanced presets.

## Settings
`lumen settings export file.json` / `import file.json`. Exports contain no passwords or tokens.
The GUI includes Black & Gold, Ocean, Emerald, and Violet color themes.

## Troubleshooting
Logs: launcher `lumen.log` and `game.log` in the log folder (secrets are redacted). Attach them when asking for help.
