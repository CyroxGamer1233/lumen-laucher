"""Secure credential storage.

Refresh tokens live ONLY in the OS keystore (Windows Credential Locker,
macOS Keychain, Secret Service/KWallet). If no secure backend exists we
refuse to persist rather than fall back to plaintext.
The JSON index holds non-secret metadata only.
Offline profiles are NOT stored here (see profiles.py).
"""
from __future__ import annotations
import json, time
from pathlib import Path

SERVICE = "lumen-launcher"


class NoSecureStorage(RuntimeError):
    pass


def _kr():
    import keyring
    from keyring.backends import fail
    if isinstance(keyring.get_keyring(), fail.Keyring):
        raise NoSecureStorage("No OS keystore available; sign in each session or install a Secret Service provider.")
    return keyring


class AccountStore:
    def __init__(self, index_path: Path):
        self.index_path = index_path

    def _read(self) -> dict:
        try:
            return json.loads(self.index_path.read_text("utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _write(self, d: dict) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2), "utf-8")
        tmp.replace(self.index_path)

    def save_microsoft(self, uuid: str, username: str, refresh_token: str) -> None:
        _kr().set_password(SERVICE, uuid, refresh_token)
        d = self._read()
        d[uuid] = {"username": username, "owned_verified_at": int(time.time())}
        self._write(d)

    def load_refresh_token(self, uuid: str) -> str | None:
        return _kr().get_password(SERVICE, uuid)

    def remove(self, uuid: str) -> None:
        try:
            _kr().delete_password(SERVICE, uuid)
        except Exception:
            pass
        d = self._read()
        d.pop(uuid, None)
        self._write(d)

    def list_accounts(self) -> dict:
        return self._read()

    def find(self, selector: str) -> str | None:
        """Resolve a UUID (dashed or not) or a case-insensitive username to a stored UUID."""
        sel = selector.strip().lower()
        for uuid, meta in self._read().items():
            if sel in (uuid.lower(), uuid.lower().replace("-", ""), str(meta.get("username", "")).lower()):
                return uuid
        return None

    def has_verified_ownership(self) -> bool:
        """True after one successful Microsoft sign-in that owns the game (index only; no keystore)."""
        return any(isinstance(v, dict) and "owned_verified_at" in v for v in self._read().values())
