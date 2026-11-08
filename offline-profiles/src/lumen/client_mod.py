from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_client_mod() -> Path | None:
    candidates = []
    configured = os.environ.get("LUMEN_CLIENT_MOD")
    if configured:
        candidates.append(Path(configured).expanduser())

    here = Path(__file__).resolve()
    candidates.extend([
        here.parents[4] / "client-mod" / "build" / "libs",
        Path.home() / ".lumen_launcher" / "client-mod",
        here.parent / "client-mod",
    ])

    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() == ".jar":
            return candidate
        if candidate.is_dir():
            jars = sorted(candidate.glob("*.jar"))
            if jars:
                return jars[-1]
    return None


def install_client_mod(mods_directory: str | Path) -> Path | None:
    source = find_client_mod()
    if source is None:
        return None

    target_dir = Path(mods_directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return target
