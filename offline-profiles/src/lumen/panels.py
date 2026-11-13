from __future__ import annotations

import hashlib
import os
import platform
import re
import socket
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QApplication, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from lumen import config, paths
from packaging.version import Version

RELEASE_API = "https://api.github.com/repos/CyroxGamer1233/lumen-laucher/releases/latest"
INSTALLER_NAME = "LumenOfflineSetup.exe"


class ServerCheckWorker(QThread):
    result = Signal(str)

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host, self.port = host, port

    def run(self):
        started = time.perf_counter()
        try:
            with socket.create_connection((self.host, self.port), timeout=4):
                latency = round((time.perf_counter() - started) * 1000)
            self.result.emit(f"ONLINE  •  {self.host}:{self.port}  •  {latency} ms")
        except OSError:
            self.result.emit(f"OFFLINE  •  {self.host}:{self.port}")


class ServersTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Servers")
        title.setObjectName("title")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.address = QLineEdit()
        self.address.setPlaceholderText("play.example.net:25565")
        row.addWidget(self.address, 1)
        self.check = QPushButton("CHECK STATUS")
        self.check.clicked.connect(self.check_server)
        row.addWidget(self.check)
        layout.addLayout(row)

        self.status = QLabel("No server checked")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        layout.addStretch()

    def check_server(self):
        raw = self.address.text().strip()
        host, _, port_text = raw.partition(":")
        try:
            port = int(port_text or "25565")
        except ValueError:
            self.status.setText("Invalid port")
            return
        if not host:
            self.status.setText("Enter a server address")
            return

        self.check.setEnabled(False)
        self.status.setText("Checking...")
        self.worker = ServerCheckWorker(host, port)
        self.worker.result.connect(self.server_result)
        self.worker.finished.connect(lambda: self.check.setEnabled(True))
        self.worker.start()

    def server_result(self, result: str):
        self.status.setText(result)


class UpdateWorker(QThread):
    checked = Signal(object)
    failed = Signal(str)

    def __init__(self, current_version: str, download: bool = False):
        super().__init__()
        self.current_version = current_version
        self.download = download

    def run(self):
        temporary = None
        try:
            if platform.system() != "Windows":
                raise RuntimeError("Installer updates are currently available for Windows.")
            import httpx

            headers = {"Accept": "application/vnd.github+json", "User-Agent": "LumenLauncher"}
            with httpx.Client(timeout=45, follow_redirects=True, headers=headers) as client:
                response = client.get(RELEASE_API)
                response.raise_for_status()
                release = response.json()
                tag = str(release.get("tag_name", "")).strip()
                version = tag[1:] if tag.lower().startswith("v") else tag
                if not version or Version(version) <= Version(self.current_version):
                    self.checked.emit((None, None))
                    return

                assets = {str(asset.get("name")): asset for asset in release.get("assets", [])}
                installer = assets.get(INSTALLER_NAME)
                checksum = assets.get(INSTALLER_NAME + ".sha256")
                if not installer or not checksum:
                    raise RuntimeError("The latest release is missing its installer or SHA-256 file.")

                offer = {
                    "version": version,
                    "url": installer["browser_download_url"],
                    "checksum_url": checksum["browser_download_url"],
                    "notes": release.get("body") or "",
                }
                if not self.download:
                    self.checked.emit((offer, None))
                    return

                checksum_response = client.get(offer["checksum_url"])
                checksum_response.raise_for_status()
                match = re.search(r"\b([0-9a-fA-F]{64})\b", checksum_response.text)
                if not match:
                    raise RuntimeError("The release checksum file is invalid.")
                expected_hash = match.group(1).lower()

                destination = paths.data_dir() / "updates"
                destination.mkdir(parents=True, exist_ok=True)
                target = destination / f"LumenOfflineSetup-{version}.exe"
                temporary = target.with_suffix(target.suffix + ".part")
                digest = hashlib.sha256()
                with client.stream("GET", offer["url"]) as download:
                    download.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in download.iter_bytes(1024 * 256):
                            output.write(chunk)
                            digest.update(chunk)
                if digest.hexdigest().lower() != expected_hash:
                    temporary.unlink(missing_ok=True)
                    raise RuntimeError("Downloaded installer failed its SHA-256 check.")
                os.replace(temporary, target)
                self.checked.emit((offer, target))
        except Exception as error:
            self.failed.emit(str(error))




class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = paths.config_path()
        self.settings = config.load(self.path)

        layout = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("title")
        layout.addWidget(title)

        form = QFormLayout()
        self.version = QLineEdit(self.settings.mc_version)
        self.loader = QComboBox()
        self.loader.addItems(["vanilla", "fabric", "forge"])
        self.loader.setCurrentText(self.settings.loader)
        self.profile = QComboBox()
        self.profile.addItems(["low_end", "balanced", "high_end"])
        self.profile.setCurrentText(self.settings.jvm_profile)
        self.ram = QSpinBox()
        self.ram.setRange(0, 32768)
        self.ram.setSuffix(" MB (0 = auto)")
        self.ram.setValue(self.settings.ram_mb or 0)
        self.java = QLineEdit(self.settings.java_path or "")
        self.java.setPlaceholderText("Automatic Java runtime")
        self.offline = QCheckBox("Prefer local assets and avoid authentication")
        form.addRow("Minecraft version", self.version)
        form.addRow("Loader", self.loader)
        form.addRow("JVM profile", self.profile)
        form.addRow("Memory", self.ram)
        form.addRow("Java path", self.java)
        form.addRow("", self.offline)
        layout.addLayout(form)

        self.save_button = QPushButton("SAVE SETTINGS")
        self.save_button.clicked.connect(self.save)
        layout.addWidget(self.save_button)

        self.auto_update = QCheckBox("Automatically download and install verified Windows updates")
        self.auto_update.setToolTip(
            "The official GitHub release installer replaces app files only. "
            "Profiles, settings, skins, and instances stay in your user data folders."
        )
        layout.addWidget(self.auto_update)
        self.update_button = QPushButton("CHECK FOR UPDATES")
        self.update_button.clicked.connect(self.check_updates)
        layout.addWidget(self.update_button)
        self.download_update_button = QPushButton("DOWNLOAD UPDATE")
        self.download_update_button.setEnabled(False)
        self.download_update_button.clicked.connect(self.download_update)
        layout.addWidget(self.download_update_button)
        self.install_update_button = QPushButton("INSTALL DOWNLOADED UPDATE")
        self.install_update_button.setEnabled(False)
        self.install_update_button.clicked.connect(self.install_staged_update)
        layout.addWidget(self.install_update_button)
        self.update_status = QLabel("Checks official GitHub releases and verifies the installer SHA-256.")
        self.update_status.setObjectName("muted")
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        self.update_worker = None
        self.available_update = None
        self.staged_installer = None
        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        layout.addStretch()

    def _start_update_worker(self, download: bool, on_finished=None):
        from lumen import __version__
        self.update_worker = UpdateWorker(__version__, download)
        self.update_worker.checked.connect(self.update_result)
        self.update_worker.failed.connect(self.update_failed)
        if on_finished is not None:
            self.update_worker.finished.connect(on_finished)
        self.update_worker.start()

    def check_updates(self):
        self.update_button.setEnabled(False)
        self.download_update_button.setEnabled(False)
        self.install_update_button.setEnabled(False)
        self.update_status.setText("Checking the latest Lumen Windows release...")
        self._start_update_worker(
            self.auto_update.isChecked(),
            lambda: self.update_button.setEnabled(True),
        )

    def download_update(self):
        if not self.available_update:
            return
        self.download_update_button.setEnabled(False)
        self.update_status.setText(f"Downloading and verifying Lumen {self.available_update['version']}...")
        self._start_update_worker(
            True,
            lambda: self.download_update_button.setEnabled(
                self.staged_installer is None
            ),
        )

    def update_result(self, result):
        offer, downloaded = result
        if offer is None:
            self.available_update = None
            self.staged_installer = None
            self.download_update_button.setEnabled(False)
            self.install_update_button.setEnabled(False)
            self.update_status.setText("You are up to date.")
            return
        self.available_update = offer
        if downloaded:
            self.staged_installer = downloaded
            self.install_update_button.setText(f"INSTALL LUMEN {offer['version']}")
            self.install_update_button.setEnabled(True)
            self.update_status.setText(
                f"Lumen {offer['version']} downloaded and SHA-256 verified. "
                "Your launcher data remains outside the install folder."
            )
            if self.auto_update.isChecked():
                QTimer.singleShot(500, lambda: self.install_staged_update(automatic=True))
        else:
            self.download_update_button.setText(f"DOWNLOAD LUMEN {offer['version']}")
            self.download_update_button.setEnabled(True)
            self.update_status.setText(
                f"Lumen {offer['version']} is available. "
                "Download & Install will verify the installer before opening it."
            )

    def install_staged_update(self, automatic: bool = False):
        if not self.staged_installer or not self.staged_installer.is_file():
            self.update_status.setText("Download the update first.")
            return
        if not automatic:
            answer = QMessageBox.question(
                self,
                "Install Lumen update",
                "The launcher will close and run the verified installer. "
                "Your offline accounts, settings, skins, and Minecraft instances are kept "
                "in your user data folders. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            subprocess.Popen(
                [
                    str(self.staged_installer),
                    "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                    "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
                ],
                cwd=str(self.staged_installer.parent),
                close_fds=True,
            )
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except OSError as error:
            self.update_status.setText(f"Could not start installer: {error}")

    def update_failed(self, message):
        self.download_update_button.setEnabled(bool(self.available_update))
        self.update_status.setText(f"Update check failed: {message}")

    def save(self):
        self.settings.mc_version = self.version.text().strip() or "1.21.1"
        self.settings.loader = self.loader.currentText()
        self.settings.jvm_profile = self.profile.currentText()
        self.settings.ram_mb = self.ram.value() or None
        self.settings.java_path = self.java.text().strip() or None
        config.save(self.settings, self.path)
        self.status.setText("Settings saved")
