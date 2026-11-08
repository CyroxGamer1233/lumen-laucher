from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import minecraft_launcher_lib
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QPlainTextEdit, QScrollArea, QSplashScreen, QTabWidget, QTextBrowser, QVBoxLayout, QWidget
)

from lumen import logging_setup, paths
from lumen.assets import AssetDownloader
from lumen.catalog import ModrinthCatalog
from lumen.offline_launcher import OfflineLauncher
from lumen.instance_panel import InstancesTab
from lumen.instances import InstanceStore
from lumen.offline_profiles import OfflineProfileDB
from lumen.panels import ServersTab, SettingsTab


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    return label


def title_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("title")
    return label


STYLE = """
QMainWindow, QWidget { background:#0b0d10; color:#f6f1e7; font-size:13px; }
QLabel#title { font-size:25px; font-weight:800; color:#ffffff; }
QLabel#muted { color:#9ba4b0; }
QFrame, QListWidget, QPlainTextEdit {
    background:#13171c; border:1px solid #2c333c; border-radius:10px;
}
QPushButton {
    background:#f2b90b; color:#111318; border:0; border-radius:7px;
    padding:9px 16px; font-weight:800;
}
QPushButton:hover { background:#ffd34d; }
QPushButton:pressed { background:#c99200; }
QPushButton#secondary { background:#20262e; color:#f6f1e7; border:1px solid #3d4652; }
QPushButton#account { background:#242b34; color:#ffd34d; border:1px solid #f2b90b; }
QComboBox, QLineEdit {
    background:#151a20; color:#f6f1e7; border:1px solid #3d4652;
    border-radius:7px; padding:8px;
}
QTabWidget::pane { border:0; }
QTabBar::tab { background:#151a20; color:#aab3bf; padding:11px 18px; margin:2px; border-radius:6px; }
QTabBar::tab:selected { background:#f2b90b; color:#111318; }
QProgressBar { background:#151a20; border:1px solid #3d4652; border-radius:5px; text-align:center; }
QProgressBar::chunk { background:#f2b90b; border-radius:5px; }
"""


class DownloadWorker(QThread):
    progress = Signal(str, int, int)
    done = Signal()
    failed = Signal(str)

    def __init__(self, directory: Path, version: str):
        super().__init__()
        self.directory, self.version = directory, version

    def run(self):
        try:
            AssetDownloader(self.directory).install_version(
                self.version,
                lambda status, current, maximum:
                    self.progress.emit(status, current, maximum),
            )
            self.done.emit()
        except Exception as error:
            self.failed.emit(str(error))


class VersionWorker(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory

    def run(self):
        try:
            versions = minecraft_launcher_lib.utils.get_available_versions(self.directory)
            self.loaded.emit([str(v["id"]) for v in versions])
        except Exception as error:
            self.failed.emit(str(error))


class ContentDetailsDialog(QDialog):
    def __init__(self, project: dict, download_callback, parent=None):
        super().__init__(parent)
        self.project = project
        self.download_callback = download_callback
        self.setWindowTitle(project.get("title", "Content details"))
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label(project.get("title", "Content details")))
        layout.addWidget(muted_label(
            f'{project.get("project_type", "content").title()}  •  '
            f'{project.get("downloads", 0):,} downloads'
        ))

        icon_url = project.get("icon_url")
        if icon_url:
            try:
                with urllib.request.urlopen(icon_url, timeout=8) as response:
                    image = QPixmap()
                    image.loadFromData(response.read())
                    image = image.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                    icon = QLabel()
                    icon.setPixmap(image)
                    layout.addWidget(icon)
            except Exception:
                pass

        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        description = project.get("description", "No description available.")
        gallery = project.get("gallery", [])
        html = f"<h3>{project.get('title', '')}</h3><p>{description}</p>"
        if gallery:
            html += "<p><b>Screenshots:</b> " + " • ".join(
                item.get("title", "image") for item in gallery
            ) + "</p>"
        text.setHtml(html)
        layout.addWidget(text, 1)

        if gallery:
            screenshots = QHBoxLayout()
            for entry in gallery[:6]:
                url = entry.get("url")
                if not url:
                    continue
                try:
                    with urllib.request.urlopen(url, timeout=8) as response:
                        picture = QPixmap()
                        picture.loadFromData(response.read())
                        picture = picture.scaled(
                            180, 110,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        image_label = QLabel()
                        image_label.setPixmap(picture)
                        screenshots.addWidget(image_label)
                except Exception:
                    continue
            layout.addLayout(screenshots)

        buttons = QHBoxLayout()
        download = QPushButton("DOWNLOAD TO SELECTED INSTANCE")
        download.clicked.connect(self.download)
        buttons.addWidget(download)
        close = QPushButton("CLOSE")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def download(self):
        self.download_callback()
        self.accept()


class CatalogWorker(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, project_type: str, query: str):
        super().__init__()
        self.project_type, self.query = project_type, query

    def run(self):
        try:
            values = ModrinthCatalog().search(self.project_type, self.query)
            for value in values:
                icon_url = value.get("icon_url")
                if icon_url:
                    try:
                        with urllib.request.urlopen(icon_url, timeout=8) as response:
                            value["_icon_bytes"] = response.read()
                    except Exception:
                        value["_icon_bytes"] = b""
            self.loaded.emit(values)
        except Exception as error:
            self.failed.emit(str(error))


class CatalogTab(QWidget):
    def __init__(self, project_type: str, version_provider, instance_provider=None, parent=None):
        super().__init__(parent)
        self.project_type = project_type
        self.version_provider = version_provider
        self.instance_provider = instance_provider
        self.catalog = ModrinthCatalog()
        self.instance_store = InstanceStore(paths.config_path().parent / "instances.json")
        self.results_data = []

        layout = QVBoxLayout(self)
        layout.addWidget(title_label(project_type.title() + " browser"))
        layout.addWidget(muted_label(
            "Search Modrinth, inspect results, then download compatible content."
        ))

        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search Modrinth...")
        row.addWidget(self.query, 1)
        search = QPushButton("SEARCH")
        search.clicked.connect(self.search)
        row.addWidget(search)
        layout.addLayout(row)

        version_row = QHBoxLayout()
        version_row.addWidget(QLabel("Target Minecraft version"))
        self.version_box = QComboBox()
        self.version_box.setEditable(True)
        self.version_box.addItem("1.21.1")
        version_row.addWidget(self.version_box, 1)
        layout.addLayout(version_row)

        self.instance_box = QComboBox()
        self.instance_box.setEditable(False)
        for instance in self.instance_store.instances:
            self.instance_box.addItem(instance.name)
        instance_row = QHBoxLayout()
        instance_row.addWidget(QLabel("Target instance"))
        instance_row.addWidget(self.instance_box, 1)
        layout.addLayout(instance_row)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self.open_details)
        layout.addWidget(self.results, 1)
        self.status = muted_label("Ready")
        layout.addWidget(self.status)

        self.download = QPushButton("DOWNLOAD SELECTED")
        self.download.clicked.connect(self.download_selected)
        layout.addWidget(self.download)

    def search(self):
        self.status.setText("Searching Modrinth...")
        self.search_worker = CatalogWorker(self.project_type, self.query.text().strip())
        self.search_worker.loaded.connect(self.set_results)
        self.search_worker.failed.connect(lambda error: self.status.setText(error))
        self.search_worker.start()

    def set_results(self, values: list):
        self.results_data = values
        self.results.clear()
        for value in values:
            item = QListWidgetItem(
                f'{value.get("title", value.get("project_id", "Unknown"))}  '
                f'•  {value.get("description", "")[:100]}'
            )
            icon_data = value.get("_icon_bytes", b"")
            if icon_data:
                image = QImage.fromData(icon_data)
                if not image.isNull():
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
            item.setToolTip(value.get("description", ""))
            self.results.addItem(item)
        self.status.setText(f"{len(values)} result(s)")

    def open_details(self, _item):
        row = self.results.currentRow()
        if row < 0 or row >= len(self.results_data):
            return
        try:
            project = self.catalog.project(self.results_data[row]["project_id"])
            dialog = ContentDetailsDialog(project, self.download_selected, self)
            dialog.exec()
        except Exception as error:
            self.status.setText(str(error))

    def download_selected(self):
        row = self.results.currentRow()
        if row < 0 or row >= len(self.results_data):
            self.status.setText("Select an item first")
            return
        try:
            version = self.version_box.currentText().strip()
            if not version:
                raise ValueError("Select a Minecraft version first")
            instance_name = self.instance_box.currentText().strip()
            if not instance_name:
                raise RuntimeError("Create and select an instance first")
            instance_root = paths.data_dir() / "instances" / instance_name
            folder = {
                "mod": "mods",
                "shader": "shaderpacks",
                "modpack": "modpacks",
            }.get(self.project_type, self.project_type)
            destination = instance_root / folder
            result = self.catalog.download(
                self.results_data[row]["project_id"], version, destination
            )
            if self.project_type == "modpack" and result.suffix.lower() == ".mrpack":
                minecraft_launcher_lib.mrpack.install_mrpack(
                    result,
                    paths.minecraft_dir(),
                    modpack_directory=destination.parent,
                )
            self.status.setText(f"Downloaded and installed {result.name}")
        except Exception as error:
            self.status.setText(str(error))


class AccountDialog(QDialog):
    def __init__(self, db: OfflineProfileDB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Offline account")
        self.setMinimumWidth(360)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Enter local username")
        form = QFormLayout(self)
        form.addRow("Username", self.name)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        try:
            self.profile = self.db.add_profile(self.name.text())
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Invalid account", str(error))
            return
        super().accept()


class LumenWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lumen Launcher")
        self.resize(1120, 720)

        self.minecraft_dir = Path(paths.minecraft_dir())
        self.profile_db = OfflineProfileDB(
            Path(paths.config_path()).parent / "offline_profiles.json"
        )
        self.worker = None
        self.current_instance = None

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)

        header = QHBoxLayout()
        brand = QLabel("LUMEN")
        brand.setObjectName("title")
        header.addWidget(brand)
        header.addWidget(muted_label("  OFFLINE CLIENT"))
        header.addStretch()
        self.account_button = QPushButton()
        self.account_button.setObjectName("account")
        self.account_button.clicked.connect(self.manage_account)
        header.addWidget(self.account_button)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.home_tab(), "Home")
        self.tabs.addTab(InstancesTab(self.select_instance), "Instances")
        self.tabs.addTab(CatalogTab("mod", lambda: self.home_version.currentText()), "Mods")
        self.tabs.addTab(CatalogTab("shader", lambda: self.home_version.currentText()), "Shaders")
        self.tabs.addTab(CatalogTab("modpack", lambda: self.home_version.currentText(), lambda: self.current_instance), "Modpacks")
        self.tabs.addTab(ServersTab(), "Servers")
        self.tabs.addTab(SettingsTab(), "Settings")
        outer.addWidget(self.tabs)

        self.refresh_account()
        self.refresh_instances()

    def home_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Play locally")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(muted_label(
            "Prepared assets launch without Microsoft, Xbox, or downloader calls."
        ))

        card = QWidget()
        grid = QGridLayout(card)
        grid.addWidget(QLabel("Instance"), 0, 0)
        self.home_version = QComboBox()
        self.home_version.setEditable(True)
        self.home_version.addItem("No instances")
        grid.addWidget(self.home_version, 0, 1)

        self.play_button = QPushButton("PLAY OFFLINE")
        self.play_button.clicked.connect(self.launch_game)
        grid.addWidget(self.play_button, 1, 0, 1, 2)
        layout.addWidget(card)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Launcher status will appear here...")
        layout.addWidget(self.log, 1)
        return page

    def versions_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(title_label("Minecraft versions"))
        layout.addWidget(muted_label(
            "Choose a version and download it during the online provisioning stage."
        ))

        row = QHBoxLayout()
        self.version_box = QComboBox()
        self.version_box.setEditable(True)
        self.version_box.addItem("1.21.1")
        row.addWidget(self.version_box, 1)
        self.download_button = QPushButton("DOWNLOAD")
        self.download_button.clicked.connect(self.download_version)
        row.addWidget(self.download_button)
        layout.addLayout(row)

        self.download_status = QLabel("Ready")
        self.download_status.setObjectName("muted")
        layout.addWidget(self.download_status)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 0)
        self.download_progress.setVisible(False)
        layout.addWidget(self.download_progress)

        self.installed = QListWidget()
        layout.addWidget(QLabel("Installed locally"))
        layout.addWidget(self.installed, 1)
        self.refresh_installed()
        return page

    def placeholder_tab(self, name: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(title_label(name))
        layout.addWidget(muted_label(
            f"{name} management is ready for the next provider integration."
        ))
        layout.addStretch()
        return page

    def refresh_instances(self):
        store = InstanceStore(paths.config_path().parent / "instances.json")
        self.home_version.clear()
        if not store.instances:
            self.home_version.addItem("No instances")
            self.current_instance = None
            return
        for instance in store.instances:
            self.home_version.addItem(instance.name)
        self.current_instance = store.instances[0]
        self.home_version.setCurrentText(self.current_instance.name)

    def select_instance(self, instance):
        self.current_instance = instance
        self.home_version.setCurrentText(instance.name)

    def refresh_installed(self):
        if not hasattr(self, "installed"):
            return
        self.installed.clear()
        versions = self.minecraft_dir / "versions"
        if versions.exists():
            for item in sorted(versions.iterdir()):
                if item.is_dir() and (item / f"{item.name}.json").exists():
                    self.installed.addItem(item.name)

    def refresh_account(self):
        try:
            profile = self.profile_db.get_active_profile()
            self.account_button.setText(f"●  {profile.username}  •  OFFLINE")
        except RuntimeError:
            self.account_button.setText("＋  ADD OFFLINE ACCOUNT")

    def manage_account(self):
        dialog = AccountDialog(self.profile_db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_account()
            self.log.appendPlainText(
                f"Offline account ready: {dialog.profile.username}"
            )

    def download_version(self):
        version = self.version_box.currentText().strip()
        if not version:
            return

        self.download_button.setEnabled(False)
        self.download_progress.setVisible(True)
        self.download_progress.setRange(0, 0)
        self.download_status.setText(f"Downloading {version}...")
        self.worker = DownloadWorker(self.minecraft_dir, version)
        self.worker.progress.connect(self.download_progress_update)
        self.worker.done.connect(self.download_done)
        self.worker.failed.connect(self.download_failed)
        self.worker.start()

    def download_progress_update(self, status: str, current: int, maximum: int):
        self.download_status.setText(f"{status}: {current}/{maximum}" if maximum else status)
        if maximum:
            self.download_progress.setRange(0, maximum)
            self.download_progress.setValue(current)

    def download_done(self):
        self.download_button.setEnabled(True)
        self.download_progress.setVisible(False)
        self.download_status.setText("Download complete")
        self.refresh_installed()
        self.log.appendPlainText("Local assets synchronized.")

    def download_failed(self, message: str):
        self.download_button.setEnabled(True)
        self.download_progress.setVisible(False)
        self.download_status.setText("Download failed")
        QMessageBox.critical(self, "Download failed", message)

    def launch_game(self):
        try:
            profile = self.profile_db.get_active_profile()
            if self.current_instance is None:
                raise RuntimeError("Create an instance first")
            if (
                self.current_instance.loader in ("fabric", "forge")
                and not self.current_instance.installed_version
            ):
                raise RuntimeError(
                    "Install this instance first so its real loader version is selected"
                )
            version = (
                self.current_instance.installed_version
                or self.current_instance.version
            )
            instance_root = paths.data_dir() / "instances" / self.current_instance.name
            jvm = [
                f"-Xmx{self.current_instance.ram_mb}M",
                f"-Xms{min(1024, self.current_instance.ram_mb)}M",
            ]
            launcher = OfflineLauncher(self.minecraft_dir, self.profile_db)
            launcher.launch(
                version,
                profile=profile,
                jvm_arguments=jvm,
                game_directory=instance_root,
                output=self.log.appendPlainText,
            )
            self.log.appendPlainText(
                f"Launching {self.current_instance.name} ({version}) as {profile.username}..."
            )
        except Exception as error:
            QMessageBox.warning(self, "Cannot launch offline", str(error))


def main() -> int:
    logging_setup.setup(paths.log_dir())
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    pixmap = QPixmap(640, 340)
    pixmap.fill(QColor("#0b0d10"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#f2b90b"))
    painter.setFont(QFont("Consolas", 34, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), 0x84, "LUMEN")
    painter.setPen(QColor("#9ba4b0"))
    painter.setFont(QFont("Consolas", 12))
    painter.drawText(0, 225, 640, 30, 0x84, "Preparing your local Minecraft workspace...")
    painter.end()
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    splash.show()
    app.processEvents()

    window = LumenWindow()

    effect = QGraphicsOpacityEffect(window)
    window.setGraphicsEffect(effect)
    fade = QPropertyAnimation(effect, b"opacity", window)
    fade.setDuration(420)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    window._fade_animation = fade
    window.show()
    fade.start()
    QTimer.singleShot(900, splash.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
