from __future__ import annotations

import hashlib
import json
import os
import ssl
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

import minecraft_launcher_lib

from .catalog import open_url
from .java_runtime import ensure_java


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
MAX_DOWNLOAD_WORKERS = 8


@dataclass(frozen=True)
class ModpackInstallResult:
    name: str
    minecraft_version: str
    loader: str
    installed_version: str


def _safe_destination(root: Path, relative_name: str) -> Path:
    if not relative_name or "\\" in relative_name or "\x00" in relative_name:
        raise RuntimeError(f"Unsafe modpack path: {relative_name!r}")
    relative = PurePosixPath(relative_name)
    if relative.is_absolute() or ":" in relative_name or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"Unsafe modpack path: {relative_name!r}")
    root = root.resolve()
    destination = root.joinpath(*relative.parts).resolve()
    try:
        destination.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"Modpack path escapes the instance folder: {relative_name}") from error
    return destination


def _download_one(root: Path, entry: dict) -> tuple[Path, bool]:
    relative_name = str(entry.get("path", ""))
    destination = _safe_destination(root, relative_name)
    hashes = entry.get("hashes") or {}
    algorithm = "sha1" if hashes.get("sha1") else "sha512" if hashes.get("sha512") else None
    expected = hashes.get(algorithm) if algorithm else None

    if destination.is_file() and expected:
        digest = hashlib.new(algorithm, destination.read_bytes()).hexdigest()
        if digest.lower() == expected.lower():
            return destination, True

    urls = entry.get("downloads") or []
    if not urls:
        raise RuntimeError(f"No download URL was provided for {relative_name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".part", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    last_error = None
    try:
        for url in urls:
            parsed = urllib.parse.urlparse(str(url))
            if parsed.scheme != "https" or not parsed.netloc:
                raise RuntimeError(f"Refusing non-HTTPS modpack URL for {relative_name}")
            try:
                request = urllib.request.Request(
                    str(url), headers={"User-Agent": "LumenLauncher/1.0"}
                )
                digest = hashlib.new(algorithm) if algorithm else None
                with open_url(request, timeout=45) as response, temporary.open("wb") as sink:
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        sink.write(chunk)
                        if digest:
                            digest.update(chunk)
                if digest and digest.hexdigest().lower() != expected.lower():
                    raise RuntimeError(f"Hash check failed for modpack file {relative_name}")
                os.replace(temporary, destination)
                return destination, False
            except ssl.SSLCertVerificationError:
                raise
            except Exception as error:
                last_error = error
                temporary.unlink(missing_ok=True)
                if url != urls[-1]:
                    time.sleep(0.35)
                    fd, temporary_name = tempfile.mkstemp(
                        prefix=destination.name + ".", suffix=".part", dir=destination.parent
                    )
                    os.close(fd)
                    temporary = Path(temporary_name)
        raise RuntimeError(f"Could not download {relative_name}: {last_error}") from last_error
    finally:
        temporary.unlink(missing_ok=True)


def _install_overrides(archive: zipfile.ZipFile, instance_root: Path) -> None:
    prefixes = ("overrides/", "client-overrides/")
    for item in archive.infolist():
        prefix = next((value for value in prefixes if item.filename.startswith(value)), None)
        if prefix is None or item.is_dir():
            continue
        relative_name = item.filename[len(prefix):]
        destination = _safe_destination(instance_root, relative_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.write_bytes(archive.read(item))
        except OSError as error:
            raise RuntimeError(
                f"Cannot write modpack override '{relative_name}' "
                f"(Windows error {getattr(error, 'winerror', 'n/a')}): {error}"
            ) from error


def install_modrinth_pack(
    archive_path: str | Path,
    minecraft_directory: str | Path,
    instance_directory: str | Path,
    status: StatusCallback,
    progress: ProgressCallback,
) -> ModpackInstallResult:
    archive_path = Path(archive_path)
    minecraft_directory = Path(minecraft_directory).expanduser().resolve()
    instance_root = Path(instance_directory).expanduser().resolve()
    instance_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(archive_path) as archive:
            if "modrinth.index.json" not in archive.namelist():
                raise RuntimeError("This .mrpack is missing modrinth.index.json")
            index = json.loads(archive.read("modrinth.index.json"))
            if index.get("formatVersion") != 1:
                raise RuntimeError(f"Unsupported Modrinth pack format: {index.get('formatVersion')}")
            dependencies = index.get("dependencies") or {}
            minecraft_version = dependencies.get("minecraft")
            if not minecraft_version:
                raise RuntimeError("The modpack does not declare a Minecraft version")

            files = []
            for entry in index.get("files", []):
                environment = entry.get("env") or {}
                if environment.get("client") == "unsupported":
                    continue
                if environment.get("client") == "optional":
                    continue
                files.append(entry)

            status(f"Preparing {len(files)} modpack files")
            progress(0, len(files))
            if files:
                finished = 0
                lock = threading.Lock()
                with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as pool:
                    futures = {
                        pool.submit(_download_one, instance_root, entry): entry
                        for entry in files
                    }
                    try:
                        for future in as_completed(futures):
                            entry = futures[future]
                            path, cached = future.result()
                            with lock:
                                finished += 1
                                progress(finished, len(files))
                            status(
                                f"{'Already ready' if cached else 'Downloaded'} "
                                f"{entry.get('path', path.name)}"
                            )
                    except Exception:
                        for future in futures:
                            future.cancel()
                        raise

            status("Applying modpack configuration files")
            _install_overrides(archive, instance_root)

        status(f"Installing Minecraft {minecraft_version}")
        current_max = [0]

        def set_max(value):
            current_max[0] = max(0, int(value))
            progress(0, current_max[0])

        def set_progress(value):
            progress(max(0, int(value)), current_max[0])

        callback = {
            "setStatus": status,
            "setProgress": set_progress,
            "setMax": set_max,
        }
        minecraft_launcher_lib.install.install_minecraft_version(
            minecraft_version, minecraft_directory, callback=callback
        )

        loader_pairs = (
            ("fabric-loader", "fabric"),
            ("forge", "forge"),
            ("neoforge", "neoforge"),
            ("quilt-loader", "quilt"),
        )
        selected = next(
            ((key, loader_id) for key, loader_id in loader_pairs if dependencies.get(key)),
            None,
        )
        if selected:
            dependency_key, loader_id = selected
            loader_version = str(dependencies[dependency_key])
            status(f"Installing {loader_id.title()} {loader_version}")
            java = ensure_java(
                minecraft_version,
                minecraft_directory,
                offline=False,
                status=status,
            )
            loader = minecraft_launcher_lib.mod_loader.get_mod_loader(loader_id)
            installed_version = loader.install(
                minecraft_version,
                minecraft_directory,
                loader_version=loader_version,
                callback=callback,
                java=java,
            )
        else:
            installed_version = minecraft_version
            loader_id = "vanilla"

        return ModpackInstallResult(
            name=str(index.get("name") or archive_path.stem),
            minecraft_version=minecraft_version,
            loader=loader_id,
            installed_version=str(installed_version),
        )
    except (OSError, zipfile.BadZipFile) as error:
        winerror = getattr(error, "winerror", None)
        details = f"Windows error {winerror}" if winerror else type(error).__name__
        raise RuntimeError(f"Modpack install failed ({details}): {error}") from error
