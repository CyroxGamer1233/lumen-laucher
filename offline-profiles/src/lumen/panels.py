from __future__ import annotations

import os
import platform
import socket
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from lumen import config, paths
from lumen.updater import updater


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
        try:
            import httpx
            manifest_url = os.environ.get("LUMEN_UPDATE_MANIFEST_URL", updater.MANIFEST_URL)
            public_key = os.environ.get("LUMEN_UPDATE_PUBLIC_KEY", updater.PUBLIC_KEY_B64)
            platform_name = "windows" if platform.system() == "Windows" else (
                "macos" if platform.system() == "Darwin" else "linux"
            )
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                update = updater.check(client, self.current_version, platform_name,
                                       manifest_url, public_key)
                if update and self.download:
                    destination = updater.download(
                        client, update, paths.data_dir() / "updates"
                    )
                    self.checked.emit((update, destination))
                else:
                    self.checked.emit((update, None))
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

        self.auto_update = QCheckBox("Automatically download verified updates")
        self.auto_update.setToolTip("Updates are staged in the Lumen data folder and never overwrite your profiles.")
        layout.addWidget(self.auto_update)
        self.update_button = QPushButton("CHECK FOR UPDATES")
        self.update_button.clicked.connect(self.check_updates)
        layout.addWidget(self.update_button)
        self.update_status = QLabel("Updater ready")
        self.update_status.setObjectName("muted")
        layout.addWidget(self.update_status)
        self.update_worker = None
        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        layout.addStretch()

    def check_updates(self):
        self.update_button.setEnabled(False)
        self.update_status.setText("Checking for signed updates...")
        from lumen import __version__
        self.update_worker = UpdateWorker(__version__, self.auto_update.isChecked())
        self.update_worker.checked.connect(self.update_result)
        self.update_worker.failed.connect(self.update_failed)
        self.update_worker.finished.connect(lambda: self.update_button.setEnabled(True))
        self.update_worker.start()

    def update_result(self, result):
        update, downloaded = result
        if update is None:
            self.update_status.setText("You are up to date.")
        elif downloaded:
            self.update_status.setText(f"Update {update.version} downloaded safely: {downloaded.name}")
        else:
            self.update_status.setText(f"Update {update.version} is available. Enable automatic download to stage it.")

    def update_failed(self, message):
        self.update_status.setText(f"Updater unavailable: {message}")

    def save(self):
        self.settings.mc_version = self.version.text().strip() or "1.21.1"
        self.settings.loader = self.loader.currentText()
        self.settings.jvm_profile = self.profile.currentText()
        self.settings.ram_mb = self.ram.value() or None
        self.settings.java_path = self.java.text().strip() or None
        config.save(self.settings, self.path)
        self.status.setText("Settings saved")
