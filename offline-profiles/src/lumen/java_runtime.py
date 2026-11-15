from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import minecraft_launcher_lib


def java_major_version(executable: str) -> int | None:
    result = subprocess.run(
        [executable, "-version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = result.stdout + result.stderr
    match = re.search(r'version\s+"([^"]+)"|openjdk\s+(\d+)', output, re.IGNORECASE)
    if not match:
        return None
    version = match.group(1)
    if version:
        parts = version.split(".", 2)
        major = int(parts[1]) if parts[0] == "1" and len(parts) > 1 else int(parts[0])
    else:
        major = int(match.group(2))
    return major if result.returncode == 0 else None


def _is_compatible(executable: str, required_major: int | None) -> bool:
    if required_major is None:
        return True
    try:
        return java_major_version(executable) == required_major
    except (OSError, subprocess.SubprocessError):
        return False


def find_java(explicit: str | None = None, required_major: int | None = None) -> str | None:
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
        if value and _is_compatible(value, required_major):
            return value
    return None


def ensure_java(
    version: str,
    minecraft_directory: str | Path,
    explicit: str | None = None,
    offline: bool = False,
    status=None,
) -> str:
    directory = Path(minecraft_directory)
    info = minecraft_launcher_lib.runtime.get_version_runtime_information(
        version, str(directory)
    )
    required_major = int(info["javaMajorVersion"]) if info else None

    if explicit:
        found = find_java(explicit, required_major)
        if found:
            return found
        requested = f"Java {required_major}" if required_major else "a usable Java runtime"
        raise RuntimeError(f"The configured Java path is not a compatible {requested} runtime.")

    if info and info.get("name"):
        name = info["name"]
        executable = minecraft_launcher_lib.runtime.get_executable_path(name, str(directory))
        if executable and Path(executable).is_file():
            return str(executable)

        if not offline:
            if status:
                status(f"Downloading Java {required_major} runtime...")
            minecraft_launcher_lib.runtime.install_jvm_runtime(name, str(directory))
            executable = minecraft_launcher_lib.runtime.get_executable_path(name, str(directory))
            if executable and Path(executable).is_file():
                return str(executable)

    found = find_java(required_major=required_major)
    if found:
        return found

    requested = f"Java {required_major}" if required_major else "a Java runtime"
    if offline:
        raise RuntimeError(
            f"{requested} is not installed for Minecraft {version}. "
            "Connect once and install this version's runtime before playing offline."
        )
    if info and info.get("name"):
        raise RuntimeError(
            f"Could not install or locate {requested} for Minecraft {version}."
        )
    raise RuntimeError(f"Could not determine a compatible Java runtime for Minecraft {version}.")
