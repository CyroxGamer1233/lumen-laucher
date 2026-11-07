from __future__ import annotations

from pathlib import Path
from typing import Callable

import minecraft_launcher_lib

ProgressCallback = Callable[[str, int, int], None]


class AssetDownloader:
    """Online provisioning phase; the resulting directory can be used offline."""

    def __init__(self, minecraft_directory: str | Path):
        self.minecraft_directory = Path(minecraft_directory).expanduser()
        self.minecraft_directory.mkdir(parents=True, exist_ok=True)
        self.maximum = 0

    def install_version(
        self,
        version: str,
        progress: ProgressCallback | None = None,
    ) -> None:
        def set_status(status: str) -> None:
            if progress:
                progress(status, 0, self.maximum)

        def set_progress(current: int) -> None:
            if progress:
                progress("Downloading", current, self.maximum)

        def set_maximum(maximum: int) -> None:
            self.maximum = maximum
            if progress:
                progress("Preparing", 0, maximum)

        minecraft_launcher_lib.install.install_minecraft_version(
            version,
            self.minecraft_directory,
            callback={
                "setStatus": set_status,
                "setProgress": set_progress,
                "setMax": set_maximum,
            },
        )
