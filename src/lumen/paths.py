"""Per-user directories (no admin rights, nothing written next to the executable)."""
from __future__ import annotations
from pathlib import Path
from platformdirs import user_config_dir, user_data_dir, user_log_dir
from . import APP_NAME


def _mk(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    return _mk(Path(user_data_dir(APP_NAME, appauthor=False)))


def minecraft_dir() -> Path:
    """Shared libraries/assets/versions (mirrors the vanilla .minecraft layout)."""
    return _mk(data_dir() / "minecraft")


def instance_dir(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_.") or "default"
    return _mk(data_dir() / "instances" / safe)


def config_path() -> Path:
    return _mk(Path(user_config_dir(APP_NAME, appauthor=False))) / "settings.json"


def accounts_index_path() -> Path:
    return _mk(Path(user_config_dir(APP_NAME, appauthor=False))) / "accounts.json"


def log_dir() -> Path:
    return _mk(Path(user_log_dir(APP_NAME, appauthor=False)))
