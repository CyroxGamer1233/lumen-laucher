"""Local offline profile manager.

Profiles live in their own JSON file (``offline_profiles.json``), completely separate from the
production account index and from the OS keystore. Nothing in here imports ``keyring`` or ``httpx``,
so an offline launch can never touch live credentials or the network by accident.
The file holds non-secret data only (name, deterministic UUID, timestamps).
"""
from __future__ import annotations
import json, time
from pathlib import Path
from .models import Account
from .offline import offline_account, offline_uuid, valid_username

SCHEMA = 1


class ProfileError(ValueError):
    pass


class OfflineProfileStore:
    def __init__(self, path: Path):
        self.path = path

    # -- persistence -------------------------------------------------------------------------
    def _read(self) -> dict:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (FileNotFoundError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        profiles = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}
        last = raw.get("last_used") if isinstance(raw.get("last_used"), str) else None
        return {"schema": SCHEMA, "profiles": profiles, "last_used": last}

    def _write(self, d: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, sort_keys=True), "utf-8")
        tmp.replace(self.path)                              # atomic

    # -- API ---------------------------------------------------------------------------------
    def names(self) -> list[str]:
        return sorted(self._read()["profiles"])

    def last_used(self) -> str | None:
        d = self._read()
        return d["last_used"] if d["last_used"] in d["profiles"] else None

    def add(self, username: str) -> Account:
        acct = offline_account(username)                    # validates the name
        d = self._read()
        d["profiles"].setdefault(username, {"uuid": acct.uuid, "created_at": int(time.time())})
        self._write(d)
        return acct

    def get(self, username: str) -> Account:
        if username not in self._read()["profiles"]:
            raise ProfileError(f"No offline profile named {username!r} (see: lumen profile list)")
        return offline_account(username)

    def remove(self, username: str) -> bool:
        d = self._read()
        if d["profiles"].pop(username, None) is None:
            return False
        if d["last_used"] == username:
            d["last_used"] = None
        self._write(d)
        return True

    def select(self, username: str | None, default: str = "Player") -> Account:
        """Pick the profile for a launch (explicit > last used > default), creating it on first use.

        The choice is persisted to the local profile file only.
        """
        name = username or self.last_used() or default
        if not valid_username(name):
            raise ProfileError("Username must be 3-16 chars: letters, digits, underscore")
        acct = self.add(name)
        d = self._read()
        d["last_used"] = name
        self._write(d)
        return acct

    def uuid_for(self, username: str) -> str:
        return offline_uuid(username)
