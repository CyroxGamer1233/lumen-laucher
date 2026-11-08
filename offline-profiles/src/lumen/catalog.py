from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://api.modrinth.com/v2"


class ModrinthCatalog:
    def __init__(self, user_agent: str = "LumenLauncher/1.0"):
        self.headers = {"User-Agent": user_agent}

    def _request(self, url: str) -> dict | list:
        request = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def search(self, project_type: str, query: str = "", limit: int = 20) -> list[dict]:
        params = urllib.parse.urlencode({
            "query": query,
            "limit": limit,
            "project_type": project_type,
        })
        result = self._request(f"{API}/search?{params}")
        return list(result.get("hits", []))

    def project(self, project_id: str) -> dict:
        return dict(self._request(f"{API}/project/{project_id}"))

    def download(
        self,
        project_id: str,
        minecraft_version: str,
        destination: str | Path,
        loader: str = "fabric",
    ) -> Path:
        params = urllib.parse.urlencode({
            "game_versions": json.dumps([minecraft_version]),
            "loaders": json.dumps([loader]),
            "limit": 1,
        })
        versions = self._request(f"{API}/project/{project_id}/version?{params}")
        if not versions:
            raise RuntimeError("No compatible file was found for this version")

        version = versions[0]
        primary = next(
            (file for file in version["files"] if file.get("primary")),
            version["files"][0],
        )

        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        output = target / Path(primary["filename"]).name

        request = urllib.request.Request(primary["url"], headers=self.headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            output.write_bytes(response.read())

        return output
