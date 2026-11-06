"""Minecraft profile and skin lookup."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

SESSION = "https://sessionserver.mojang.com/session/minecraft/profile"


@dataclass
class Skin:
    uuid: str
    name: str
    skin_url: str | None = None
    cape_url: str | None = None
    model: str = "classic"


def lookup(uuid: str, client=None) -> Skin:
    own = client is None
    if client is None:
        import httpx
        client = httpx.Client(timeout=15)
    response = client.get(f"{SESSION}/{uuid.replace('-', '')}")
    response.raise_for_status()
    data = response.json()
    result = Skin(data["id"], data["name"])
    for prop in data.get("properties", []):
        if prop.get("name") != "textures":
            continue
        decoded = json.loads(base64.b64decode(prop["value"]).decode("utf-8"))
        textures = decoded.get("textures", {})
        result.skin_url = (textures.get("SKIN") or {}).get("url")
        result.cape_url = (textures.get("CAPE") or {}).get("url")
        result.model = ((textures.get("SKIN") or {}).get("metadata") or {}).get("model", "classic")
    if own:
        client.close()
    return result

