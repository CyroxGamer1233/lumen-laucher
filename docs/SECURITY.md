# Security and compliance

## Credentials
- Microsoft refresh token: OS keystore only (`keyring`). No plaintext fallback; if none exists the user signs in per session.
- Minecraft access token: memory only, handed to the game as a launch argument, never written to logs (`logging_setup.redact`).
- Settings/exports contain no secrets. Machine-specific paths are stripped on export.
- No client secret ships in the app (public client, device-code flow).

## Network and supply chain
- HTTPS only; downloads go to `.part`, are hash-verified (SHA-1 Mojang, SHA-512 Modrinth, SHA-256 updates), then atomically moved.
- Updates: Ed25519-signed manifest, public key compiled in, private key offline/CI secret. Compromise of the host cannot push a forged update.
- Archives are extracted with zip-slip protection. Filenames from APIs are reduced to basenames.
- Pin dependencies (`pip-compile --generate-hashes`) and run `pip-audit` in CI.

## Sandboxing (honest limits)
Minecraft mods are arbitrary code; a JVM is not a sandbox. Mitigations: install only from Modrinth with hash checks, show the source of every mod, run the game as a normal user process, never with admin rights. Optional hardening per OS: Flatpak or `bubblewrap` on Linux, an AppContainer/low-integrity token on Windows (research-grade effort), App Sandbox on macOS (breaks mod loading in practice). Treat these as stretch goals.

## Compliance
- Authenticate with the official Microsoft/Xbox/Minecraft Services chain. You must register your own Azure app and get it approved for Minecraft Services; check Mojang's current process.
- Download game files from Mojang's servers; never bundle or mirror them.
- Offline mode is for owners who want to play single-player/LAN or on servers that allow it. This launcher unlocks it only after one verified ownership sign-in. That gate is a design choice, not a Mojang requirement. Do not implement username spoofing for online-mode servers or account-sharing features.
- Follow the Minecraft EULA and Usage Guidelines (branding, commercial use, mod distribution) and each server's rules.
- Client features are limited to information (FPS HUD) and cosmetics. No reach, xray, auto-clicking, velocity or other advantage features, no anti-cheat evasion, no hiding the client brand from servers.
- Privacy: error reporting is opt-in and produces a local bundle (redacted log + version info) the user reviews before sending.

## Signing
Windows: Authenticode (EV helps SmartScreen). macOS: Developer ID + notarization (`build/make_dmg.sh`). Linux: detached GPG signature on tarball/AppImage.
