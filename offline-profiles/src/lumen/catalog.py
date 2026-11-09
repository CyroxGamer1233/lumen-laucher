from __future__ import annotations

import hashlib
import json
import ssl
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

import truststore


API = "https://api.modrinth.com/v2"
TLS_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def open_url(url: str | urllib.request.Request, timeout: float = 20):
    """Open HTTPS resources with the operating system's verified CA store."""
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

    def list_versions(self, project_id: str) -> list[dict]:
        params = urllib.parse.urlencode({"limit": 100, "include_changelog": "false"})
        return list(self._request(f"{API}/project/{project_id}/version?{params}"))

    def download(
        self,
        project_id: str,
        minecraft_version: str,
        destination: str | Path,
        loader: str | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        filters = {
            "game_versions": json.dumps([minecraft_version]),
            "limit": 1,
            "include_changelog": "false",
        }
        if loader:
            filters["loaders"] = json.dumps([loader])
        versions = self._request(
            f"{API}/project/{project_id}/version?{urllib.parse.urlencode(filters)}"
        )
        if not versions:
            compatible_loader = loader or "compatible loaders"
            raise RuntimeError(
                f"No {compatible_loader} file supports Minecraft {minecraft_version}"
            )

        version = versions[0]
        files = version.get("files", [])
        if not files:
            raise RuntimeError("The selected Modrinth version has no downloadable files")
        primary = next((item for item in files if item.get("primary")), files[0])

        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        filename = Path(primary["filename"]).name
        if not filename or filename in {".", ".."}:
            raise RuntimeError("Modrinth returned an invalid file name")
        output = target / filename

        hashes = primary.get("hashes", {})
        algorithm = next(
            (name for name in ("sha512", "sha1") if hashes.get(name)),
            None,
        )
        expected_hash = hashes.get(algorithm) if algorithm else None
        if output.is_file() and expected_hash:
            existing = hashlib.new(algorithm, output.read_bytes()).hexdigest()
            if existing.lower() == expected_hash.lower():
                size = output.stat().st_size
                if progress:
                    progress(size, size)
                return output

        request = urllib.request.Request(primary["url"], headers=self.headers)
        fd, temporary_name = tempfile.mkstemp(
            prefix=filename + ".", suffix=".part", dir=target
        )
        temporary = Path(temporary_name)
        digest = hashlib.new(algorithm) if algorithm else None
        try:
            with open_url(request, timeout=60) as response, open(fd, "wb", closefd=True) as sink:
                total = int(response.headers.get("Content-Length", 0) or primary.get("size", 0))
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

            if digest and digest.hexdigest().lower() != expected_hash.lower():
                raise RuntimeError(f"Downloaded file failed its {algorithm} integrity check")
            temporary.replace(output)
            return output
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
