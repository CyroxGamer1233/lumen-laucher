"""Signed auto-update.

Manifest = {"payload": {...}, "signature": "<base64 Ed25519 over canonical payload JSON>"}.
The public key is compiled into the launcher; the private key stays offline / in CI secrets.
Even if the update host is compromised, an attacker cannot forge a valid manifest.
"""
from __future__ import annotations
import base64, json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import Version
from ..net.verify import download_verified

PUBLIC_KEY_B64 = "REPLACE_WITH_BASE64_ED25519_PUBLIC_KEY"
MANIFEST_URL = "https://example.invalid/lumen/latest.json"


class UpdaterNotConfigured(RuntimeError):
    pass


@dataclass
class Update:
    version: str
    url: str
    sha256: str
    notes: str


def is_configured(url: str = MANIFEST_URL, public_key_b64: str = PUBLIC_KEY_B64) -> bool:
    return not (public_key_b64.startswith("REPLACE_") or urlparse(url).hostname in (None, "", "example.invalid")
                or (urlparse(url).hostname or "").endswith(".invalid"))


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def parse_manifest(manifest: dict, public_key_b64: str, current: str, platform: str) -> Update | None:
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    payload = manifest["payload"]
    try:
        pub.verify(base64.b64decode(manifest["signature"]), canonical(payload))
    except InvalidSignature:
        raise ValueError("Update manifest signature is invalid") from None
    if Version(payload["version"]) <= Version(current):
        return None
    asset = payload["assets"][platform]
    return Update(payload["version"], asset["url"], asset["sha256"], payload.get("notes", ""))


def check(client, current: str, platform: str, url: str = MANIFEST_URL,
          public_key_b64: str = PUBLIC_KEY_B64) -> Update | None:
    if not is_configured(url, public_key_b64):
        raise UpdaterNotConfigured("Updater is not configured: set PUBLIC_KEY_B64 and MANIFEST_URL in updater.py.")
    r = client.get(url)
    r.raise_for_status()
    return parse_manifest(r.json(), public_key_b64, current, platform)


def download(client, update: Update, dest_dir: Path) -> Path:
    """Stage + verify. Applying happens on next start (a running exe can't replace itself on Windows)."""
    name = Path(urlparse(update.url).path).name      # ignore any ?query / #fragment
    if not name:
        raise ValueError("Update URL has no file name")
    return download_verified(client, update.url, dest_dir / name, update.sha256, "sha256")
