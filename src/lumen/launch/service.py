"""Install + command building on top of minecraft-launcher-lib (MIT).

Game files come from Mojang's own servers (piston-meta / libraries / assets);
we never bundle or redistribute Mojang binaries. minecraft-launcher-lib verifies
the SHA-1 hashes that Mojang publishes in the version manifest.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Callable
from .. import __version__
from ..auth.models import Account
from ..config import Settings
from .jvm import build_jvm_args

log = logging.getLogger("lumen.launch")
Status = Callable[[str], None]


def _callbacks(on_status: Status | None) -> dict:
    cb = on_status or (lambda s: None)
    return {"setStatus": cb, "setProgress": lambda v: None, "setMax": lambda v: None}


def prepare(mc_version: str, loader: str, mc_dir: Path, on_status: Status | None = None) -> str:
    """Install vanilla + loader and return the launchable version id."""
    import minecraft_launcher_lib as mll
    cbs = _callbacks(on_status)
    mll.install.install_minecraft_version(mc_version, str(mc_dir), callback=cbs)
    if loader == "fabric":
        if not mll.fabric.is_minecraft_version_supported(mc_version):
            raise RuntimeError(f"Fabric does not support {mc_version}")
        loader_ver = mll.fabric.get_latest_loader_version()
        mll.fabric.install_fabric(mc_version, str(mc_dir), loader_version=loader_ver, callback=cbs)
        return f"fabric-loader-{loader_ver}-{mc_version}"
    if loader == "forge":
        fv = mll.forge.find_forge_version(mc_version)
        if not fv:
            raise RuntimeError(f"No Forge build for {mc_version}")
        mll.forge.install_forge_version(fv, str(mc_dir), callback=cbs)
        return mll.forge.forge_to_installed_version(fv)
    return mc_version


def ensure_java_runtime(version_id: str, settings: Settings, mc_dir: Path,
                        on_status: Status | None = None) -> str | None:
    """Install Mojang's matching Java runtime unless the user selected Java."""
    if settings.java_path:
        return settings.java_path
    import minecraft_launcher_lib as mll
    info = mll.utils.get_version_runtime_information(version_id, str(mc_dir))
    if not info:
        raise RuntimeError("Minecraft runtime information is unavailable")
    if on_status:
        on_status(f"Installing Java {info.get('javaMajorVersion', '')} runtime...")
    mll.runtime.install_jvm_runtime(info["name"], str(mc_dir))
    return info["name"]


def build_command(version_id: str, account: Account, settings: Settings,
                  mc_dir: Path, game_dir: Path) -> list[str]:
    import minecraft_launcher_lib as mll
    java_major = 21
    try:
        info = mll.utils.get_version_runtime_information(version_id, str(mc_dir))
        if info:
            java_major = int(info.get("javaMajorVersion", java_major))
            if not settings.java_path:
                ensure_java_runtime(version_id, settings, mc_dir)
    except Exception as e:                      # fall back to system Java
        log.warning("Mojang runtime lookup failed: %s", e)
    options: dict = {
        "username": account.username,
        "uuid": account.uuid,
        "token": account.access_token,
        "launcherName": "Lumen",
        "launcherVersion": __version__,
        "gameDirectory": str(game_dir),
        "jvmArguments": build_jvm_args(settings.jvm_profile, settings.ram_mb, java_major=java_major),
    }
    if settings.java_path:
        options["executablePath"] = settings.java_path
    return mll.command.get_minecraft_command(version_id, str(mc_dir), options)
