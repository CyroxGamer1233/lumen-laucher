"""Install + command building on top of minecraft-launcher-lib (MIT).

Game files come from Mojang's own servers (piston-meta / libraries / assets);
we never bundle or redistribute Mojang binaries. minecraft-launcher-lib verifies
the SHA-1 hashes that Mojang publishes in the version manifest.

``offline=True`` paths never touch the network: they only inspect what is already installed.
"""
from __future__ import annotations
import logging, shutil
from pathlib import Path
from typing import Callable
from .. import __version__
from ..auth.models import Account
from ..auth.offline import OFFLINE_TOKEN
from ..config import Settings
from .jvm import build_jvm_args
from .localcheck import installed_version_id

log = logging.getLogger("lumen.launch")
Status = Callable[[str], None]


def _callbacks(on_status: Status | None) -> dict:
    cb = on_status or (lambda s: None)
    return {"setStatus": cb, "setProgress": lambda v: None, "setMax": lambda v: None}


def prepare(mc_version: str, loader: str, mc_dir: Path, on_status: Status | None = None,
            offline: bool = False, loader_version: str | None = None) -> str:
    """Install vanilla + loader and return the launchable version id.

    offline=True performs NO network access: it returns the id of an already-installed version
    or raises with instructions for pre-seeding the install.
    """
    if offline:
        vid = installed_version_id(mc_dir, mc_version, loader, loader_version)
        if vid is None:
            pin = f" (loader {loader_version})" if loader_version else ""
            raise RuntimeError(
                f"{loader} {mc_version}{pin} is not installed in {mc_dir}. Run one online launch "
                "first, or copy a populated Minecraft directory into place.")
        return vid
    import minecraft_launcher_lib as mll
    cbs = _callbacks(on_status)
    mll.install.install_minecraft_version(mc_version, str(mc_dir), callback=cbs)
    if loader == "fabric":
        if not mll.fabric.is_minecraft_version_supported(mc_version):
            raise RuntimeError(f"Fabric does not support {mc_version}")
        loader_ver = loader_version or mll.fabric.get_latest_loader_version()
        mll.fabric.install_fabric(mc_version, str(mc_dir), loader_version=loader_ver, callback=cbs)
        return f"fabric-loader-{loader_ver}-{mc_version}"
    if loader == "forge":
        fv = mll.forge.find_forge_version(mc_version)
        if not fv:
            raise RuntimeError(f"No Forge build for {mc_version}")
        mll.forge.install_forge_version(fv, str(mc_dir), callback=cbs)
        return mll.forge.forge_to_installed_version(fv)
    return mc_version


def resolve_java(version_id: str, settings: Settings, mc_dir: Path, offline: bool = False,
                 on_status: Status | None = None) -> tuple[int, str | None]:
    """Return (java major version, executable or None to let minecraft-launcher-lib choose).

    Order: user-selected java_path > Mojang's bundled runtime (installed on demand, online only)
    > system Java. Failures are reported, not swallowed.
    """
    import minecraft_launcher_lib as mll
    say = on_status or (lambda s: None)
    info = None
    try:
        info = mll.utils.get_version_runtime_information(version_id, str(mc_dir))
    except Exception as e:
        log.warning("Mojang runtime lookup failed: %s", e)
    major = int(info.get("javaMajorVersion", 21)) if info else 21
    if settings.java_path:
        return major, settings.java_path
    if not info:
        exe = shutil.which("java")
        if not exe:
            raise RuntimeError("No Java runtime found. Install Java or set java_path.")
        say(f"Mojang runtime info unavailable; using system Java: {exe}")
        return major, exe

    name = info["name"]
    getter = getattr(mll.runtime, "get_executable_path", None)

    def locate() -> str | None:
        if getter is None:
            return None
        try:
            p = getter(name, str(mc_dir))
        except Exception:
            return None
        return p if p and Path(p).exists() else None

    exe = locate()
    if exe is None and not offline:
        say(f"Installing Java {major} runtime...")
        mll.runtime.install_jvm_runtime(name, str(mc_dir))
        exe = locate()
    if exe is None and getter is not None:
        exe = shutil.which("java")
        if not exe:
            raise RuntimeError(f"Java runtime {name} is not installed and no system Java was found.")
        say(f"Mojang runtime {name} not installed; using system Java: {exe}")
    return major, exe


def build_options(account: Account, settings: Settings, game_dir: Path, jvm_args: list[str],
                  executable: str | None = None) -> dict:
    """Options dict for minecraft_launcher_lib.command.get_minecraft_command()."""
    if account.kind == "offline":
        options: dict = {
            "username": account.username,
            "uuid": account.uuid,
            "token": OFFLINE_TOKEN,
            "meta": {"name": account.username, "type": "legacy"},
        }
    else:
        options = {"username": account.username, "uuid": account.uuid, "token": account.access_token}
    options.update({
        "launcherName": "Lumen",
        "launcherVersion": __version__,
        "gameDirectory": str(game_dir),
        "jvmArguments": jvm_args,
    })
    if executable:
        options["executablePath"] = executable
    return options


def apply_user_type(cmd: list[str], user_type: str) -> list[str]:
    """minecraft-launcher-lib hardcodes --userType msa; rewrite it for offline ("legacy") sessions."""
    out = list(cmd)
    for i, arg in enumerate(out[:-1]):
        if arg == "--userType":
            out[i + 1] = user_type
    return out


def build_command(version_id: str, account: Account, settings: Settings, mc_dir: Path, game_dir: Path,
                  offline: bool | None = None, on_status: Status | None = None) -> list[str]:
    import minecraft_launcher_lib as mll
    offline = (account.kind == "offline") if offline is None else offline
    major, exe = resolve_java(version_id, settings, mc_dir, offline=offline, on_status=on_status)
    jvm = build_jvm_args(settings.jvm_profile, settings.ram_mb, java_major=major)
    options = build_options(account, settings, game_dir, jvm, exe)
    cmd = mll.command.get_minecraft_command(version_id, str(mc_dir), options)
    return apply_user_type(cmd, "legacy") if account.kind == "offline" else cmd


def ensure_java_runtime(version_id: str, settings: Settings, mc_dir: Path,
                        on_status: Status | None = None) -> str | None:
    """Backward-compatible wrapper: returns the Java executable to use (None = let the library choose)."""
    return resolve_java(version_id, settings, mc_dir, offline=False, on_status=on_status)[1]
