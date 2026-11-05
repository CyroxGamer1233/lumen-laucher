"""Make sure an instance has Fabric API, the Lumen client mod and (optionally) the performance pack."""
from __future__ import annotations

import json
import logging
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from . import modrinth
from .manifest import scan_folder

log = logging.getLogger("lumen.mods")
SUPPORTED_CLIENT_MC = "1.21.1"          # the bundled Lumen mod is built for this version
STATE_FILE = ".lumen-installed.json"
Status = Callable[[str], None]


def bundled_dir() -> Path | None:
    """Frozen app: <bundle>/bundled_mods. Dev checkout: client-mod/build/libs."""
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "bundled_mods")
    candidates.append(Path(__file__).resolve().parents[3] / "client-mod" / "build" / "libs")
    return next((c for c in candidates if c.is_dir()), None)


def find_client_jar() -> Path | None:
    d = bundled_dir()
    if not d:
        return None
    jars = sorted(p for p in d.glob("lumen-client-*.jar")
                  if not p.name.endswith(("-sources.jar", "-dev.jar")))
    return jars[-1] if jars else None


def ensure_client_mod(mods_dir: Path, mc_version: str) -> str:
    if mc_version != SUPPORTED_CLIENT_MC:
        return f"Lumen HUD mod is built for {SUPPORTED_CLIENT_MC}; skipped for {mc_version}"
    jar = find_client_jar()
    if jar is None:
        return "Lumen HUD mod jar not found; skipped"
    mods_dir.mkdir(parents=True, exist_ok=True)
    for old in mods_dir.glob("lumen-client-*.jar"):
        if old.name != jar.name:
            old.unlink()
    dest = mods_dir / jar.name
    if not dest.exists() or dest.stat().st_size != jar.stat().st_size:
        shutil.copy2(jar, dest)
    return f"Lumen HUD mod ready ({jar.name})"


def ensure_modrinth_mods(mods_dir: Path, mc_version: str, slugs: list[str], on_status: Status) -> None:
    mods_dir.mkdir(parents=True, exist_ok=True)
    state_path = mods_dir / STATE_FILE
    try:
        state = json.loads(state_path.read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        state = {}
    client = None
    for slug in slugs:
        fn = state.get(slug)
        if fn and (mods_dir / fn).exists():
            continue
        try:
            client = client or modrinth.make_client()
            on_status(f"Installing {slug}...")
            state[slug] = modrinth.install(client, slug, mc_version, mods_dir).name
        except Exception as e:                      # one missing mod must not block launching
            log.warning("mod %s skipped: %s", slug, e)
            on_status(f"Skipped {slug}: {e}")
    state_path.write_text(json.dumps(state, indent=2), "utf-8")


def prepare_mods(mods_dir: Path, mc_version: str, performance: bool, on_status: Status) -> None:
    on_status(ensure_client_mod(mods_dir, mc_version))
    slugs = ["fabric-api"] + (list(modrinth.PERFORMANCE_PACK) if performance else [])
    ensure_modrinth_mods(mods_dir, mc_version, slugs, on_status)


def has_mod(mods_dir: Path, mod_id: str) -> bool:
    return mods_dir.is_dir() and any(m.id == mod_id for m in scan_folder(mods_dir))
