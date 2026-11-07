"""Resolve and download mods from Modrinth (hash-verified, HTTPS only)."""
from __future__ import annotations
import json
from pathlib import Path
from .. import USER_AGENT
from ..net.verify import download_verified

API = "https://api.modrinth.com/v2"

# Starter "performance" pack (Modrinth project slugs); users can edit/replace.
PERFORMANCE_PACK = ["sodium", "lithium", "ferrite-core", "modernfix", "immediatelyfast", "entityculling"]


def make_client():
    import httpx
    return httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})


def resolve(client, slug: str, mc_version: str, loader: str = "fabric") -> dict:
    r = client.get(f"{API}/project/{slug}/version", params={
        "game_versions": json.dumps([mc_version]), "loaders": json.dumps([loader])})
    r.raise_for_status()
    versions = r.json()
    if not versions:
        raise LookupError(f"{slug}: no {loader} build for {mc_version}")
    v = versions[0]                                         # newest first
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    return {"slug": slug, "version": v["version_number"], "url": f["url"],
            "filename": f["filename"], "sha512": f["hashes"]["sha512"]}


def install(client, slug: str, mc_version: str, mods_dir: Path, loader: str = "fabric") -> Path:
    info = resolve(client, slug, mc_version, loader)
    name = Path(info["filename"]).name                      # strip any path components
    return download_verified(client, info["url"], mods_dir / name, info["sha512"], "sha512")
