from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import platform
import re
import subprocess

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QApplication, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
    QHeaderView, QTableWidget, QTableWidgetItem,
)

from lumen import config, paths
from lumen.server_status import parse_server_address, query_minecraft_server
from packaging.version import Version

RELEASE_API = "https://api.github.com/repos/CyroxGamer1233/lumen-laucher/releases/latest"
INSTALLER_NAME = "LumenOfflineSetup.exe"


class ServerCheckWorker(QThread):
    result = Signal(str, object, str)
    done = Signal()

    def __init__(self, addresses: list[str]):
        super().__init__()
        self.addresses = addresses

    def run(self):
        for address in self.addresses:
            try:
                host, port = parse_server_address(address)
                self.result.emit(address, query_minecraft_server(host, port), "")
            except (OSError, RuntimeError, ValueError) as error:
                self.result.emit(address, None, str(error))
        self.done.emit()


POPULAR_SERVERS = (
    "mc.hypixel.net",
    "play.cubecraft.net",
    "mccentral.org",
)


class ServersTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Servers")
        title.setObjectName("title")
        layout.addWidget(title)

        controls = QHBoxLayout()
        self.address = QLineEdit()
        self.address.setPlaceholderText("play.example.net:25565")
        controls.addWidget(self.address, 1)
        self.add_button = QPushButton("ADD SERVER")
        self.add_button.clicked.connect(self.add_server)
        controls.addWidget(self.add_button)
        layout.addLayout(controls)

        actions = QHBoxLayout()
        self.popular = QComboBox()
        self.popular.addItem("Popular servers", "")
        for address in POPULAR_SERVERS:
            self.popular.addItem(address, address)
        actions.addWidget(self.popular, 1)
        self.add_popular_button = QPushButton("ADD POPULAR")
        self.add_popular_button.clicked.connect(self.add_popular)
        actions.addWidget(self.add_popular_button)
        self.check = QPushButton("REFRESH STATUS")
        self.check.clicked.connect(self.check_server)
        actions.addWidget(self.check)
        layout.addLayout(actions)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter servers or MOTD")
        self.search.textChanged.connect(self.apply_filter)
        filters.addWidget(self.search, 1)
        self.online_filter = QComboBox()
        self.online_filter.addItems(["All servers", "Online", "Offline"])
        self.online_filter.currentIndexChanged.connect(self.apply_filter)
        filters.addWidget(self.online_filter)
        self.remove_button = QPushButton("REMOVE SELECTED")
        self.remove_button.clicked.connect(self.remove_selected)
        filters.addWidget(self.remove_button)
        layout.addLayout(filters)

        self.status = QLabel("No server checked")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Server", "Status", "Version", "Players", "Ping", "MOTD"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.select_server)
        layout.addWidget(self.table, 1)
        self.server_path = paths.config_path().parent / "servers.json"
        self.save_error = None
        self.server_data = self._load_servers()
        self._populate_table()
        layout.addStretch()

    def _load_servers(self) -> dict[str, dict]:
        try:
            data = json.loads(self.server_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {address: {} for address in POPULAR_SERVERS}
        except (OSError, ValueError) as error:
            self.status.setText(f"Could not load saved servers: {error}")
            return {address: {} for address in POPULAR_SERVERS}
        if not isinstance(data, dict):
            self.status.setText("Saved server list is invalid; using popular presets.")
            return {address: {} for address in POPULAR_SERVERS}
        return {
            str(address): details if isinstance(details, dict) else {}
            for address, details in data.items()
            if isinstance(address, str)
        }

    def _save_servers(self):
        try:
            self.server_path.parent.mkdir(parents=True, exist_ok=True)
            self.server_path.write_text(
                json.dumps(self.server_data, indent=2), encoding="utf-8"
            )
            self.save_error = None
        except OSError as error:
            self.save_error = f"Could not save server list: {error}"
            self.status.setText(self.save_error)

    def _populate_table(self):
        self.table.setRowCount(len(self.server_data))
        for row, (address, details) in enumerate(self.server_data.items()):
            status = details.get("status", "Not checked")
            values = [
                address,
                status,
                details.get("version", "—"),
                details.get("players", "—"),
                details.get("ping", "—"),
                details.get("motd", "—"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, address)
                    favicon = details.get("favicon")
                    if isinstance(favicon, str):
                        try:
                            image_data = base64.b64decode(
                                favicon.partition(",")[2], validate=True
                            )
                        except (ValueError, binascii.Error):
                            image_data = b""
                        icon = QPixmap()
                        if image_data and icon.loadFromData(image_data, "PNG"):
                            item.setIcon(QIcon(icon.scaled(28, 28)))
                self.table.setItem(row, column, item)
        self.apply_filter()

    def add_server(self):
        address = self.address.text().strip()
        try:
            host, port = parse_server_address(address)
        except ValueError as error:
            self.status.setText(str(error))
            return
        normalized = f"[{host}]:{port}" if ":" in host else (
            f"{host}:{port}" if port != 25565 else host
        )
        if normalized in self.server_data:
            self.status.setText("That server is already in your list.")
            return
        self.server_data[normalized] = {}
        self._save_servers()
        self._populate_table()
        if self.save_error:
            return
        self.address.clear()
        self.status.setText(f"Added {normalized}. Refresh to query its live status.")

    def add_popular(self):
        address = self.popular.currentData()
        if not address:
            self.status.setText("Choose a popular server first.")
            return
        if address in self.server_data:
            self.status.setText("That server is already in your list.")
            return
        self.server_data[address] = {}
        self._save_servers()
        self._populate_table()
        if self.save_error:
            return
        self.status.setText(f"Added {address}. Refresh to query its live status.")

    def remove_selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            self.status.setText("Select a server to remove.")
            return
        self.server_data.pop(item.data(Qt.ItemDataRole.UserRole), None)
        self._save_servers()
        self._populate_table()

    def select_server(self, row: int, _column: int):
        item = self.table.item(row, 0)
        if item:
            self.address.setText(item.data(Qt.ItemDataRole.UserRole))

    def apply_filter(self, *_):
        query = self.search.text().casefold()
        mode = self.online_filter.currentText()
        for row in range(self.table.rowCount()):
            text = " ".join(
                self.table.item(row, column).text()
                for column in range(self.table.columnCount())
                if self.table.item(row, column)
            ).casefold()
            status = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            visible = query in text
            visible &= mode == "All servers" or status == mode.upper()
            self.table.setRowHidden(row, not visible)

    def check_server(self):
        if not self.server_data:
            self.status.setText("Add a server before refreshing its status.")
            return
        addresses = list(self.server_data)
        self.check.setEnabled(False)
        self.status.setText(f"Querying {len(addresses)} Minecraft server(s)...")
        self.worker = ServerCheckWorker(addresses)
        self.worker.result.connect(self.server_result)
        self.worker.done.connect(self.refresh_done)
        self.worker.finished.connect(lambda: self.check.setEnabled(True))
        self.worker.start()

    def server_result(self, address: str, result: dict | None, error: str):
        if result is None:
            details = {"status": "OFFLINE", "version": "—", "players": "—", "ping": "—",
                       "motd": error or "No status response"}
        else:
            details = {
                "status": "ONLINE",
                "version": result["version"],
                "players": f'{result["players_online"]}/{result["players_max"]}',
                "ping": f'{result["latency_ms"]} ms',
                "motd": result["motd"] or "(No MOTD)",
                "favicon": result["favicon"],
            }
        self.server_data[address] = details
        self._save_servers()
        self._populate_table()

    def refresh_done(self):
        if self.save_error:
            self.status.setText(self.save_error)
            return
        online = sum(
            details.get("status") == "ONLINE"
            for details in self.server_data.values()
        )
        self.status.setText(f"Status updated: {online} online / {len(self.server_data)} listed.")


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
    theme_changed = Signal(str)

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
        self.theme = QComboBox()
        self.theme.addItem("Gold / Lumen", "gold")
        self.theme.addItem("Midnight Blue", "midnight")
        self.theme.addItem("Emerald", "emerald")
        self.theme.addItem("Violet", "violet")
        self.theme.addItem("Crimson", "crimson")
        self.theme.addItem("Arctic", "arctic")
        self.theme.setCurrentIndex(max(0, self.theme.findData(getattr(self.settings, "theme", "gold"))))
        self.theme.currentIndexChanged.connect(lambda _index: self.theme_changed.emit(self.theme.currentData()))
        self.close_on_launch = QCheckBox("Close launcher after Minecraft starts")
        self.close_on_launch.setChecked(self.settings.close_launcher_on_launch)
        self.java.setPlaceholderText("Automatic Java runtime")
        self.offline = QCheckBox("Prefer local assets and avoid authentication")
        form.addRow("Minecraft version", self.version)
        form.addRow("Loader", self.loader)
        form.addRow("JVM profile", self.profile)
        form.addRow("Memory", self.ram)
        form.addRow("Java path", self.java)
        form.addRow("Launcher theme", self.theme)
        form.addRow("After launch", self.close_on_launch)
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
        self.settings.theme = self.theme.currentData() or "gold"
        self.settings.close_launcher_on_launch = self.close_on_launch.isChecked()
        config.save(self.settings, self.path)
        self.status.setText("Settings saved")
