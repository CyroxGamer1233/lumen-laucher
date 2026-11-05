# Testing plan

## Automated (CI, every push)
- Unit tests (`tests/`): offline UUIDs, JVM args, version ranges, conflict detection, checksum/zip-slip, redaction, settings round-trip, update-signature tampering.
- Ruff lint; `pip-audit`; Gradle build of the client mod on JDK 21.
- Matrix: Windows, macOS, Ubuntu x Python 3.11/3.12.

## To add
- Auth chain tests with `httpx.MockTransport` (happy path, `authorization_pending`, `slow_down`, XSTS 2148916233/38, 404 profile).
- Integration (nightly): install Fabric for the pinned MC version into a temp dir and assert the launch command contains the expected Java major version and client jar.
- Headless smoke test of the built bundle: `Lumen --version` equivalent, start/exit.

## Manual matrix (per release)
Win 10/11, macOS (Intel + Apple Silicon), Ubuntu/Fedora (X11 + Wayland), paths with spaces and non-ASCII user names, low-RAM machine (4 GB), no keystore available, offline start, corrupted mod jar, interrupted download.

## FPS benchmark method
1. Fixed machine state: plugged in, high-performance power plan, no background updates, same resolution/render distance/simulation distance.
2. Fixed world: same seed and a datapack function that teleports along a set route (about 60 s) after a 30 s warm-up.
3. Run with `-Dlumen.bench=<file>`; the client mod writes per-frame ms plus avg FPS and 1% low on exit.
4. Run each configuration 3 times, discard the first, report median of avg FPS and 1% low. Compare: vanilla vs performance pack, each JVM profile, each heap size.
5. Frame-time spikes matter more than averages: judge GC changes by 1% lows and the worst-frame figure.
Gains vary widely by GPU/CPU and mod versions, so measure rather than assume.
