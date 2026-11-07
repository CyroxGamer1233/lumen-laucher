"""Network-free inspection of an existing install (used by offline / air-gapped launches).

Everything here only reads files under the Minecraft directory; it never imports an HTTP client.
"""
from __future__ import annotations
import json
from pathlib import Path
from packaging.version import InvalidVersion, Version


def _load(p: Path) -> dict | None:
    try:
        data = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _version_json(mc_dir: Path, vid: str) -> Path:
    return mc_dir / "versions" / vid / f"{vid}.json"


def _newest(candidates: list[tuple[str, str]]) -> str | None:
    """candidates = (version-string, version-id); return the id with the highest parsable version."""
    best: tuple[Version, str] | None = None
    for ver, vid in candidates:
        try:
            v = Version(ver)
        except InvalidVersion:
            continue
        if best is None or v > best[0]:
            best = (v, vid)
    return best[1] if best else None


def installed_version_id(mc_dir: Path, mc_version: str, loader: str,
                         loader_version: str | None = None) -> str | None:
    """Return the launchable version id if it is already installed, else None."""
    if loader == "vanilla":
        return mc_version if _version_json(mc_dir, mc_version).is_file() else None
    vdir = mc_dir / "versions"
    if loader == "fabric":
        if loader_version:
            vid = f"fabric-loader-{loader_version}-{mc_version}"
            return vid if _version_json(mc_dir, vid).is_file() else None
        prefix, suffix = "fabric-loader-", f"-{mc_version}"
        found = [(d.name[len(prefix):-len(suffix)], d.name) for d in vdir.glob(f"{prefix}*{suffix}")
                 if _version_json(mc_dir, d.name).is_file()]
        return _newest(found)
    if loader == "forge":
        prefix = f"{mc_version}-forge-"
        found = [(d.name[len(prefix):], d.name) for d in vdir.glob(f"{prefix}*")
                 if _version_json(mc_dir, d.name).is_file()]
        return _newest(found)
    return None


def _lib_relpath(lib: dict) -> str | None:
    downloads = lib.get("downloads")
    if isinstance(downloads, dict):
        art = downloads.get("artifact")
        return art.get("path") if isinstance(art, dict) else None   # no artifact -> natives only
    parts = str(lib.get("name", "")).split("@")[0].split(":")        # maven coordinates (Fabric libs)
    if len(parts) < 3:
        return None
    group, name, ver = parts[:3]
    classifier = f"-{parts[3]}" if len(parts) > 3 else ""
    return f"{group.replace('.', '/')}/{name}/{ver}/{name}-{ver}{classifier}.jar"


def verify_local_install(mc_dir: Path, version_id: str) -> list[str]:
    """Return missing files (relative to mc_dir). Empty list = ready to launch offline.

    Checks: version json (+ parent), client jar, asset index, and unconditional libraries.
    Libraries gated by OS rules or native classifiers are skipped to avoid false alarms.
    """
    top = _load(_version_json(mc_dir, version_id))
    if top is None:
        return [f"versions/{version_id}/{version_id}.json"]
    missing: list[str] = []
    chain = [top]
    base_id = version_id
    parent = top.get("inheritsFrom")
    if parent:
        base_id = str(parent)
        pj = _load(_version_json(mc_dir, base_id))
        if pj is None:
            missing.append(f"versions/{base_id}/{base_id}.json")
        else:
            chain.append(pj)
    if not (mc_dir / "versions" / base_id / f"{base_id}.jar").is_file():
        missing.append(f"versions/{base_id}/{base_id}.jar")
    for data in chain:
        ai = data.get("assetIndex")
        if isinstance(ai, dict) and ai.get("id"):
            rel = f"assets/indexes/{ai['id']}.json"
            if not (mc_dir / rel).is_file():
                missing.append(rel)
            break
    for data in chain:
        for lib in data.get("libraries", []):
            if not isinstance(lib, dict) or "rules" in lib or "natives" in lib:
                continue
            rel = _lib_relpath(lib)
            if rel and not (mc_dir / "libraries" / rel).is_file():
                missing.append(f"libraries/{rel}")
    return missing
