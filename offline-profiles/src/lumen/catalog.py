from __future__ import annotations

import hashlib
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

import truststore


API = "https://api.modrinth.com/v2"

# Use the operating system's trusted roots (including Windows' certificate store).
# Certificate verification stays enabled; this also supports enterprise-installed CAs.
TLS_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def open_url(url: str | urllib.request.Request, timeout: float = 20):
    """Open HTTPS resources with the native system trust store."""
    return urllib.request.urlopen(url, timeout=timeout, context=TLS_CONTEXT)


class ModrinthCatalog:
    def __init__(self, user_agent: str = "LumenLauncher/1.0"):
        self.headers = {"User-Agent": user_agent}

    def _request(self, url: str) -> dict | list:
        request = urllib.request.Request(url, headers=self.headers)
        with open_url(request, timeout=20) as response:
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
        progress: Callable[[int, int], None] | None = None,
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
        temporary = output.with_name(output.name + ".part")

        hashes = primary.get("hashes", {})
        algorithm = next((name for name in ("sha512", "sha1") if hashes.get(name)), None)
        digest = hashlib.new(algorithm) if algorithm else None
        request = urllib.request.Request(primary["url"], headers=self.headers)

        try:
            with open_url(request, timeout=60) as response, temporary.open("wb") as sink:
                total = int(response.headers.get("Content-Length", "0") or 0)
                current = 0
                if progress:
                    progress(current, total)
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    sink.write(chunk)
                    if digest:
                        digest.update(chunk)
                    current += len(chunk)
                    if progress:
                        progress(current, total)

            if digest and digest.hexdigest().lower() != hashes[algorithm].lower():
                raise RuntimeError(f"Downloaded file failed its {algorithm} integrity check")

            temporary.replace(output)
            return output
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
