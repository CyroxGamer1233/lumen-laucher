from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib

from .offline_profiles import OfflineProfile, OfflineProfileDB
from .java_runtime import ensure_java

OutputCallback = Callable[[str], None]


class OfflineLauncher:
    def __init__(
        self,
        minecraft_directory: str | Path,
        profiles: OfflineProfileDB,
        java_path: str = "java",
    ):
        self.minecraft_directory = Path(minecraft_directory).expanduser()
        self.profiles = profiles
        self.java_path = java_path

    def build_command(
        self,
        version: str,
        profile: OfflineProfile | None = None,
        jvm_arguments: list[str] | None = None,
    ) -> list[str]:
        profile = profile or self.profiles.get_active_profile()
        version_json = (
            self.minecraft_directory / "versions" / version / f"{version}.json"
        )
        if not version_json.exists():
            raise FileNotFoundError(
                f"{version} is not installed locally: {version_json}"
            )

        executable = ensure_java(
            version,
            self.minecraft_directory,
            explicit=self.java_path if self.java_path != "java" else None,
            offline=False,
        )

        options = {
            "username": profile.username,
            "uuid": profile.uuid,
            "token": profile.token,
            "userType": profile.user_type,
            "launcherName": "Lumen Offline",
            "launcherVersion": "1.0.0",
            "executablePath": executable,
            "defaultExecutablePath": executable,
            "jvmArguments": jvm_arguments or [],
        }

        return minecraft_launcher_lib.command.get_minecraft_command(
            version, self.minecraft_directory, options
        )

    def launch(
        self,
        version: str,
        profile: OfflineProfile | None = None,
        jvm_arguments: list[str] | None = None,
        output: OutputCallback | None = None,
    ) -> subprocess.Popen:
        process = subprocess.Popen(
            self.build_command(version, profile, jvm_arguments),
            cwd=self.minecraft_directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )

        def read_output() -> None:
            if process.stdout is not None:
                for line in process.stdout:
                    if output:
                        output(line.rstrip("\n"))

        threading.Thread(
            target=read_output,
            name="minecraft-output",
            daemon=True,
        ).start()
        return process
