"""Checksum verification, atomic downloads and zip-slip-safe extraction."""
from __future__ import annotations
import hashlib, os, zipfile
from pathlib import Path

CHUNK = 1 << 20


class ChecksumError(Exception):
    pass


def file_hash(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, expected: str, algo: str = "sha256") -> None:
    actual = file_hash(path, algo)
    if actual.lower() != expected.lower():
        raise ChecksumError(f"{path.name}: {algo} mismatch (expected {expected[:12]}..., got {actual[:12]}...)")


def download_verified(client, url: str, dest: Path, expected: str, algo: str = "sha256") -> Path:
    """Stream to dest.part, verify, then atomically move into place. HTTPS only."""
    if not url.lower().startswith("https://"):
        raise ValueError("Refusing non-HTTPS download")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.new(algo)
    with client.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        with open(part, "wb") as f:
            for chunk in r.iter_bytes(CHUNK):
                h.update(chunk)
                f.write(chunk)
    if h.hexdigest().lower() != expected.lower():
        part.unlink(missing_ok=True)
        raise ChecksumError(f"{dest.name}: {algo} mismatch")
    os.replace(part, dest)
    return dest


def safe_extract(zip_path: Path, dest: Path) -> None:
    """Extract while rejecting paths that escape dest."""
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if dest != target and dest not in target.parents:
                raise ValueError(f"Unsafe path in archive: {info.filename}")
        z.extractall(dest)
