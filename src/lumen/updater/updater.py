"""Signed auto-update.

Manifest = {"payload": {...}, "signature": "<base64 Ed25519 over canonical payload JSON>"}.
The public key is compiled into the launcher; the private key stays offline / in CI secrets.
Even if the update host is compromised, an attacker cannot forge a valid manifest.
"""
from __future__ import annotations
import base64, json
from dataclasses import dataclass
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import Version
from ..net.verify import download_verified

PUBLIC_KEY_B64 = "REPLACE_WITH_BASE64_ED25519_PUBLIC_KEY"
MANIFEST_URL = "https://example.invalid/lumen/latest.json"


@dataclass
class Update:
    version: str
    url: str
    sha256: str
    notes: str


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
    r = client.get(url)
    r.raise_for_status()
    return parse_manifest(r.json(), public_key_b64, current, platform)


def download(client, update: Update, dest_dir: Path) -> Path:
    """Stage + verify. Applying happens on next start (a running exe can't replace itself on Windows)."""
    return download_verified(client, update.url, dest_dir / Path(update.url).name, update.sha256, "sha256")
