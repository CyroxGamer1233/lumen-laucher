from __future__ import annotations

import os
import shutil
from pathlib import Path

import minecraft_launcher_lib


def find_java(explicit: str | None = None) -> str | None:
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_java = os.environ.get("LUMEN_JAVA")
    if env_java:
        candidates.append(env_java)

    names = ("java.exe", "java") if os.name == "nt" else ("java",)
    for root in (
        Path.home() / ".lumen_launcher" / "java-runtime",
        Path.home() / ".lumen_launcher" / "minecraft_files",
    ):
        candidates.extend(root / "bin" / name for name in names)

    candidates.extend(names)
    for candidate in candidates:
        value = shutil.which(str(candidate)) or (
            str(candidate) if Path(candidate).is_file() else None
        )
        if value:
            return value
    return None


def ensure_java(
    version: str,
    minecraft_directory: str | Path,
    explicit: str | None = None,
    offline: bool = False,
    status=None,
) -> str:
    found = find_java(explicit)
    if found:
        return found
    if offline:
        raise RuntimeError(
            "Java was not found. Connect once and download the Java runtime "
            "from the Versions tab, then launch offline."
        )

    directory = Path(minecraft_directory)
    info = minecraft_launcher_lib.runtime.get_version_runtime_information(
        version, str(directory)
    )
    if not info or not info.get("name"):
        raise RuntimeError(f"Could not determine the Java runtime for {version}")

    if status:
        status(f"Downloading Java {info.get('javaMajorVersion', '')} runtime...")

    minecraft_launcher_lib.runtime.install_jvm_runtime(
        info["name"], str(directory)
    )

    executable = minecraft_launcher_lib.runtime.get_executable_path(
        info["name"], str(directory)
    )
    if not executable:
        raise RuntimeError("Java runtime downloaded, but executable was not found")
    return str(executable)
