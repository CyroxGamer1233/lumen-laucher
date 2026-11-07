from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

OFFLINE_NAMESPACE = uuid.UUID("14ee085c-c073-3be6-8a3b-ac83387b003a")
OFFLINE_TOKEN = "0" * 32


@dataclass
class OfflineProfile:
    username: str
    uuid: str
    token: str = OFFLINE_TOKEN
    user_type: str = "legacy"


class OfflineProfileDB:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"profiles": {}, "active": None}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            value.setdefault("profiles", {})
            value.setdefault("active", None)
            return value
        except (OSError, json.JSONDecodeError, ValueError):
            return {"profiles": {}, "active": None}

    def _save(self) -> None:
        payload = json.dumps(self.data, indent=2, sort_keys=True)
        fd, temporary = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp",
            dir=self.path.parent, text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _validate_username(username: str) -> str:
        username = username.strip()
        if not 3 <= len(username) <= 16:
            raise ValueError("Username must contain 3-16 characters")
        if not all(c.isalnum() or c == "_" for c in username):
            raise ValueError("Username may contain only letters, digits, and '_'")
        return username

    @staticmethod
    def profile_uuid(username: str) -> str:
        return str(uuid.uuid3(OFFLINE_NAMESPACE, username))

    def add_profile(self, username: str) -> OfflineProfile:
        username = self._validate_username(username)
        profile = OfflineProfile(username, self.profile_uuid(username))
        self.data["profiles"][username] = asdict(profile)
        if self.data["active"] is None:
            self.data["active"] = username
        self._save()
        return profile

    def remove_profile(self, username: str) -> None:
        self.data["profiles"].pop(username, None)
        if self.data["active"] == username:
            self.data["active"] = next(iter(self.data["profiles"]), None)
        self._save()

    def set_active_profile(self, username: str) -> OfflineProfile:
        profile = self.data["profiles"].get(username)
        if profile is None:
            raise KeyError(f"Unknown offline profile: {username}")
        self.data["active"] = username
        self._save()
        return OfflineProfile(**profile)

    def get_active_profile(self) -> OfflineProfile:
        username = self.data.get("active")
        if not username or username not in self.data["profiles"]:
            raise RuntimeError("No active offline profile")
        return OfflineProfile(**self.data["profiles"][username])

    def list_profiles(self) -> list[OfflineProfile]:
        return [OfflineProfile(**p) for p in self.data["profiles"].values()]
