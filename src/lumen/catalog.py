"""Read-only discovery and downloads for mods, shaders, and modpacks."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import USER_AGENT
from .net.verify import download_verified

MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"


@dataclass(frozen=True)
class Project:
    source: str
    id: str
    title: str
    description: str
    project_type: str
    downloads: int
    icon_url: str | None = None
    slug: str | None = None


def _client():
    import httpx
    return httpx.Client(timeout=25, headers={"User-Agent": USER_AGENT})


def _project_type(kind: str) -> str:
    return {"mods": "mod", "shaders": "shader", "modpacks": "modpack"}.get(kind, kind)


def search_modrinth(query: str, kind: str, game_version: str, loader: str = "fabric",
                    limit: int = 20, client=None) -> list[Project]:
    own = client is None
    client = client or _client()
    facets = [[f"project_type:{_project_type(kind)}"], [f"versions:{game_version}"]]
    if kind == "mods" and loader:
        facets.append([f"categories:{loader}"])
    response = client.get(f"{MODRINTH_API}/search", params={
        "query": query, "facets": json.dumps(facets), "limit": limit,
        "index": "downloads",
    })
    response.raise_for_status()
    projects = []
    for item in response.json().get("hits", []):
        projects.append(Project(
            "Modrinth", item["project_id"], item.get("title", item["project_id"]),
            item.get("description", ""), item.get("project_type", _project_type(kind)),
            int(item.get("downloads", 0)), item.get("icon_url"), item.get("slug"),
        ))
    if own:
        client.close()
    return projects


def search_curseforge(query: str, kind: str, game_version: str, loader: str = "fabric",
                      limit: int = 20, client=None) -> list[Project]:
    """Search CurseForge when the user supplies their own API key.

    CurseForge requires an application API key; the launcher never embeds one.
    """
    key = os.environ.get("CURSEFORGE_API_KEY", "").strip()
    if not key:
        return []
    class_ids = {"mods": 6, "shaders": 6552, "modpacks": 4471}
    own = client is None
    client = client or _client()
    response = client.get(f"{CURSEFORGE_API}/mods/search", headers={"x-api-key": key},
                          params={"gameId": 432, "classId": class_ids.get(kind, 6),
                                  "searchFilter": query, "gameVersion": game_version,
                                  "modLoaderType": 4 if loader == "fabric" else None,
                                  "pageSize": limit, "sortField": 2, "sortOrder": "desc"})
    response.raise_for_status()
    projects = []
    for item in response.json().get("data", []):
        projects.append(Project(
            "CurseForge", str(item["id"]), item.get("name", str(item["id"])),
            item.get("summary", ""), kind, int(item.get("downloadCount", 0)),
            item.get("logo", {}).get("url"), item.get("slug"),
        ))
    if own:
        client.close()
    return projects


def search(query: str, kind: str, game_version: str, loader: str = "fabric",
           client=None) -> list[Project]:
    return search_modrinth(query, kind, game_version, loader, client=client)


def project_versions(project: Project, game_version: str, loader: str = "fabric", client=None) -> list[dict[str, Any]]:
    own = client is None
    client = client or _client()
    if project.source == "Modrinth":
        response = client.get(f"{MODRINTH_API}/project/{project.id}/version", params={
            "game_versions": json.dumps([game_version]),
            "loaders": json.dumps([loader]),
            "include_changelog": "false",
        })
        response.raise_for_status()
        result = response.json()
    else:
        key = os.environ.get("CURSEFORGE_API_KEY", "").strip()
        response = client.get(f"{CURSEFORGE_API}/mods/{project.id}/files",
                              headers={"x-api-key": key}, params={"gameVersion": game_version, "pageSize": 20})
        response.raise_for_status()
        result = response.json().get("data", [])
    if own:
        client.close()
    return result


def install_modrinth_version(version: dict, destination: Path, client=None) -> Path:
    files = version.get("files", [])
    primary = next((f for f in files if f.get("primary")), files[0])
    sha512 = primary.get("hashes", {}).get("sha512")
    if not sha512:
        raise ValueError("Selected file has no SHA-512 hash")
    return download_verified(client or _client(), primary["url"],
                             destination / Path(primary["filename"]).name, sha512, "sha512")

