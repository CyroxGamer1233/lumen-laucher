"""User settings. Contains NO secrets, so export/import is always safe to share."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path

SCHEMA = 1
MACHINE_SPECIFIC = {"java_path"}          # never exported
PROFILES = {"low_end", "balanced", "high_end"}
LOADERS = {"vanilla", "fabric", "forge"}
THEMES = {"gold", "ocean", "emerald", "violet"}


@dataclass
class Settings:
    # Public Azure application identifier; not a client secret.
    ms_client_id: str = ""
    mc_version: str = "1.21.1"
    loader: str = "fabric"
    jvm_profile: str = "balanced"
    ram_mb: int | None = None             # None = auto
    java_path: str | None = None          # None = Mojang runtime / PATH
    offline_username: str = "Player"
    mod_profile: str = "performance"
    theme: str = "gold"
    error_reporting: bool = False         # opt-in only


def _validate(s: Settings) -> Settings:
    s.ms_client_id = str(s.ms_client_id or "").strip()
    if s.jvm_profile not in PROFILES:
        s.jvm_profile = "balanced"
    if s.loader not in LOADERS:
        s.loader = "fabric"
    if s.theme not in THEMES:
        s.theme = "gold"
    if s.ram_mb is not None:
        s.ram_mb = max(1024, min(int(s.ram_mb), 32768))
    s.offline_username = "".join(c for c in s.offline_username if c.isalnum() or c == "_")[:16] or "Player"
    return s


def load(path: Path) -> Settings:
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return Settings()
    names = {f.name for f in fields(Settings)}
    return _validate(Settings(**{k: v for k, v in raw.items() if k in names}))


def save(s: Settings, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(_validate(s)), indent=2), "utf-8")
    tmp.replace(path)                      # atomic


def export_settings(s: Settings, dest: Path) -> None:
    data = {k: v for k, v in asdict(s).items() if k not in MACHINE_SPECIFIC}
    dest.write_text(json.dumps({"schema": SCHEMA, "app": "lumen", "settings": data}, indent=2), "utf-8")


def import_settings(src: Path, current: Settings) -> Settings:
    blob = json.loads(src.read_text("utf-8"))
    if blob.get("app") != "lumen" or blob.get("schema") != SCHEMA:
        raise ValueError("Not a compatible Lumen settings file")
    names = {f.name for f in fields(Settings)} - MACHINE_SPECIFIC
    merged = asdict(current)
    merged.update({k: v for k, v in blob.get("settings", {}).items() if k in names})
    return _validate(Settings(**merged))
