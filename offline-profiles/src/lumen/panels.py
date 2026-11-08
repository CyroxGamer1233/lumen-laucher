from __future__ import annotations

import socket
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from lumen import config, paths


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
        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        layout.addStretch()

    def save(self):
        self.settings.mc_version = self.version.text().strip() or "1.21.1"
        self.settings.loader = self.loader.currentText()
        self.settings.jvm_profile = self.profile.currentText()
        self.settings.ram_mb = self.ram.value() or None
        self.settings.java_path = self.java.text().strip() or None
        config.save(self.settings, self.path)
        self.status.setText("Settings saved")
