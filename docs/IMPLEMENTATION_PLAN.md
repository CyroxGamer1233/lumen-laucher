# Implementation plan

| # | Milestone | Exit criteria | Est. |
|---|---|---|---|
| M0 | Foundations (this repo) | Unit tests green on 3 OSes in CI; client mod compiles | 1 wk |
| M1 | Auth hardening | Azure app approved by Mojang; login, refresh, ownership check tested on real accounts; keystore verified on Win/mac/Linux | 1-2 wk |
| M2 | Install + launch | Vanilla + Fabric 1.21.1 launches on all OSes; Forge path tested; progress UI | 2 wk |
| M3 | Mod manager | Modrinth search/install/update, lockfile, conflict UI, "performance pack" profile | 2 wk |
| M4 | Client mod UI | Settings Screen (HUD position/scale/colour), keybind UI, config file shared with launcher | 2 wk |
| M5 | Updater + packaging | Signed releases, PyInstaller bundles, Inno/DMG/AppImage, code signing + notarization | 1-2 wk |
| M6 | Beta | Telemetry-free crash bundles (opt-in), docs, 20-50 tester cycle, fix-list | 2 wk |

Estimates assume one developer who knows Python; add time for Mojang approval and Apple/Windows signing setup.

Risks: Mojang API/approval changes (isolate in `auth/`); new Minecraft versions changing Java requirements (we read them from the version JSON); antivirus false positives on PyInstaller output (sign, use one-folder, submit to vendors).
