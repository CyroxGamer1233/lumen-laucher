from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Instance:
    name: str
    version: str
    loader: str = "vanilla"
    ram_mb: int = 4096
    installed_version: str | None = None
    path: str | None = None
    playtime_seconds: int = 0
    last_played: str | None = None


class InstanceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.instances = self._load()

    def _load(self) -> list[Instance]:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            return [Instance(**value) for value in values]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def save(self) -> None:
        fd, temporary = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp",
            dir=self.path.parent, text=True,
        )
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as stream:
                json.dump([asdict(item) for item in self.instances], stream, indent=2)
            Path(temporary).replace(self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def add(self, instance: Instance) -> None:
        self.instances = [
            item for item in self.instances if item.name != instance.name
        ]
        self.instances.append(instance)
        self.save()
