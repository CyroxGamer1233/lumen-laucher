from __future__ import annotations

import html
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import minecraft_launcher_lib
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QFileDialog, QPlainTextEdit, QScrollArea, QSplashScreen, QStackedWidget,
    QTextBrowser, QVBoxLayout, QWidget
)

from lumen import logging_setup, paths
from lumen.assets import AssetDownloader
from lumen.catalog import ModrinthCatalog, open_url
from lumen.offline_launcher import OfflineLauncher
from lumen.instance_panel import InstancesTab
from lumen.instances import Instance, InstanceStore
from lumen.modpack_installer import install_modrinth_pack
from lumen.client_mod import install_client_mod
from lumen.java_runtime import ensure_java
from lumen.offline_profiles import OfflineProfileDB
from lumen.panels import ServersTab, SettingsTab


def resource_path(relative_path: str) -> Path:
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return bundle_dir / relative_path


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
QListWidget#navigation {
    background:#11151a; border:1px solid #252d35; border-radius:12px; padding:8px;
}
QListWidget#navigation::item {
    color:#c3c9cd; min-height:38px; padding:5px 12px;
    border-radius:8px; margin:2px 0;
}
QListWidget#navigation::item:hover { background:#1c232a; color:#fff8e7; }
QListWidget#navigation::item:selected {
    background:#f2b90b; color:#171713; font-weight:800;
}
QWidget#downloadPanel {
    background:#11151a; border:1px solid #3d4652; border-radius:10px;
}
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
    def __init__(self, project: dict, versions: list[dict], instances: list[Instance],
                 download_callback, parent=None):
        super().__init__(parent)
        self.project = project
        self.versions = versions
        self.instances = instances
        self.download_callback = download_callback
        self.setWindowTitle(project.get("title", "Content details"))
        self.resize(820, 650)
        self.setMinimumSize(720, 560)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        heading = QHBoxLayout()
        icon = QLabel()
        icon_bytes = project.get("_icon_bytes", b"")
        if icon_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(icon_bytes)
            if not pixmap.isNull():
                icon.setPixmap(pixmap.scaled(
                    72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                heading.addWidget(icon)
        title_block = QVBoxLayout()
        title_block.addWidget(title_label(project.get("title", "Content details")))
        title_block.addWidget(muted_label(
            f'{project.get("project_type", "content").title()}  •  '
            f'{project.get("downloads", 0):,} downloads'
        ))
        heading.addLayout(title_block, 1)
        layout.addLayout(heading)

        details = QTextBrowser()
        details.setOpenExternalLinks(True)
        description = html.escape(project.get("description", "No description available."))
        project_url = html.escape(project.get("slug", ""), quote=True)
        if project_url:
            description += f'<p><a href="https://modrinth.com/{project.get("project_type", "mod")}/{project_url}">Open project page</a></p>'
        details.setHtml(f"<p>{description}</p>")
        details.setMaximumHeight(170)
        layout.addWidget(details)

        gallery_bytes = project.get("_gallery_bytes", {})
        gallery = project.get("gallery", [])
        if gallery:
            gallery_row = QHBoxLayout()
            for entry in gallery[:6]:
                image_data = gallery_bytes.get(entry.get("url"), b"")
                if not image_data:
                    continue
                picture = QPixmap()
                picture.loadFromData(image_data)
                if picture.isNull():
                    continue
                preview = QLabel()
                preview.setPixmap(picture.scaled(
                    180, 108, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                preview.setToolTip(entry.get("title", "Project screenshot"))
                gallery_row.addWidget(preview)
            if gallery_row.count():
                layout.addLayout(gallery_row)

        picker = QWidget()
        picker.setObjectName("downloadPanel")
        picker_layout = QHBoxLayout(picker)
        picker_layout.setContentsMargins(12, 12, 12, 12)
        picker_layout.setSpacing(10)

        self.instance_box = QComboBox()
        for instance in instances:
            self.instance_box.addItem(instance.name, instance.name)
        self.new_instance_name = QLineEdit()
        self.new_instance_name.setPlaceholderText("New modpack instance name")
        self.new_instance_name.setText(project.get("title", "New Modpack"))
        if not instances:
            self.instance_box.addItem("Create an instance first", None)
            self.instance_box.setEnabled(False)

        supported_versions = []
        for version in versions:
            for game_version in version.get("game_versions", []):
                if game_version not in supported_versions:
                    supported_versions.append(game_version)
        if not supported_versions:
            supported_versions = list(dict.fromkeys(item.version for item in instances))
        self.version_box = QComboBox()
        self.version_box.setEditable(True)
        self.version_box.addItems(supported_versions or ["1.21.1"])

        self.loader_box = QComboBox()
        self._loaders_for_version()
        self.version_box.currentTextChanged.connect(self._loaders_for_version)
        self.instance_box.currentIndexChanged.connect(self._sync_instance_defaults)
        self._sync_instance_defaults()

        for caption, combo in (
            ("Install to", self.instance_box),
            ("Minecraft version", self.version_box),
            ("Loader / target type", self.loader_box),
        ):
            field = QVBoxLayout()
            label = QLabel(caption)
            label.setObjectName("muted")
            field.addWidget(label)
            field.addWidget(combo)
            picker_layout.addLayout(field, 1)
        layout.addWidget(picker)
        if self.project.get("project_type") == "modpack":
            self.instance_box.setVisible(False)
            name_field = QVBoxLayout()
            name_field.addWidget(QLabel("New instance name"))
            name_field.addWidget(self.new_instance_name)
            picker_layout.addLayout(name_field, 1)
        else:
            self.new_instance_name.setVisible(False)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("CLOSE")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        download = QPushButton("DOWNLOAD / INSTALL")
        download.setEnabled(bool(instances) or self.project.get("project_type") == "modpack")
        download.clicked.connect(self.download)
        buttons.addWidget(download)
        layout.addLayout(buttons)

    def _loaders_for_version(self, _version=None):
        version = self.version_box.currentText().strip()
        loaders = []
        for entry in self.versions:
            if version and version not in entry.get("game_versions", []):
                continue
            for loader in entry.get("loaders", []):
                if loader not in loaders:
                    loaders.append(loader)
        previous = self.loader_box.currentData()
        self.loader_box.blockSignals(True)
        self.loader_box.clear()
        self.loader_box.addItem("Auto / compatible", None)
        for loader in loaders:
            label = {
                "neoforge": "NeoForge",
                "optifine": "OptiFine",
                "iris": "Iris",
                "minecraft": "Vanilla",
            }.get(loader, loader.title())
            self.loader_box.addItem(label, loader)
        match = self.loader_box.findData(previous)
        if match >= 0:
            self.loader_box.setCurrentIndex(match)
        self.loader_box.blockSignals(False)

    def _sync_instance_defaults(self, *_args):
        instance_name = self.instance_box.currentData()
        instance = next(
            (item for item in self._instances() if item.name == instance_name),
            None,
        )
        if not instance:
            return
        version_index = self.version_box.findText(instance.version)
        if version_index >= 0:
            self.version_box.setCurrentIndex(version_index)
        loader_index = self.loader_box.findData(instance.loader)
        if loader_index >= 0:
            self.loader_box.setCurrentIndex(loader_index)

    def _instances(self):
        return getattr(self, "instances", [])

    def download(self):
        instance_name = self.instance_box.currentData()
        if self.project.get("project_type") == "modpack":
            instance_name = self.new_instance_name.text().strip() or self.project.get("title", "New Modpack")
        version = self.version_box.currentText().strip()
        if not instance_name:
            QMessageBox.information(self, "Instance required", "Create or select an instance first.")
            return
        if not version:
            QMessageBox.information(self, "Version required", "Choose a Minecraft version.")
            return
        selection = {
            "instance_name": instance_name,
            "minecraft_version": version,
            "loader": self.loader_box.currentData(),
        }
        self.download_callback(self.project, selection)
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
            def fetch_icon(value):
                url = value.get("icon_url")
                if not url:
                    return value, b""
                try:
                    with open_url(url, timeout=8) as response:
                        return value, response.read(3 * 1024 * 1024)
                except Exception:
                    return value, b""

            with ThreadPoolExecutor(max_workers=8) as pool:
                for value, data in pool.map(fetch_icon, values):
                    value["_icon_bytes"] = data
            self.loaded.emit(values)
        except Exception as error:
            self.failed.emit(str(error))


class ProjectDetailsWorker(QThread):
    loaded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id

    def run(self):
        try:
            catalog = ModrinthCatalog()
            project = catalog.project(self.project_id)
            versions = catalog.list_versions(self.project_id)
            urls = []
            if project.get("icon_url"):
                urls.append(project["icon_url"])
            urls.extend(
                entry.get("url") for entry in project.get("gallery", [])
                if entry.get("url")
            )

            def fetch_image(url):
                try:
                    with open_url(url, timeout=8) as response:
                        return url, response.read(4 * 1024 * 1024)
                except Exception:
                    return url, b""

            with ThreadPoolExecutor(max_workers=8) as pool:
                images = dict(pool.map(fetch_image, dict.fromkeys(urls)))
            project["_icon_bytes"] = images.get(project.get("icon_url"), b"")
            project["_gallery_bytes"] = images
            self.loaded.emit(project, versions)
        except Exception as error:
            self.failed.emit(str(error))


class CatalogProgressDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 430)
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        self.heading = title_label(title)
        layout.addWidget(self.heading)
        self.phase = muted_label("Preparing secure download...")
        layout.addWidget(self.phase)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(20)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace;")
        layout.addWidget(self.log, 1)
        self.close_button = QPushButton("WORKING…")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

    def write(self, message: str):
        self.phase.setText(message)
        self.log.appendPlainText(message)

    def set_progress(self, current: int, maximum: int):
        if maximum <= 0:
            self.progress.setRange(0, 0)
            return
        maximum = max(1, int(maximum))
        self.progress.setRange(0, maximum)
        self.progress.setValue(min(max(0, int(current)), maximum))
        self.progress.setFormat("%p%")

    def finish(self, message: str, success: bool):
        self.write(message)
        self.close_button.setEnabled(True)
        self.close_button.setText("DONE" if success else "CLOSE")
        if success:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.progress.setFormat("Ready")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setFormat("Install failed")


class CatalogInstallWorker(QThread):
    status = Signal(str)
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, project: dict, selection: dict, project_type: str,
                 instance: Instance, instance_store_path: Path):
        super().__init__()
        self.project = project
        self.selection = selection
        self.project_type = project_type
        self.instance = instance
        self.instance_store_path = instance_store_path
        self._max = [0]

    def _set_max(self, value):
        self._max[0] = max(0, int(value))
        self.progress.emit(0, self._max[0])

    def run(self):
        try:
            version = self.selection["minecraft_version"]
            loader = self.selection.get("loader")
            catalog = ModrinthCatalog()
            project_id = (self.project.get("project_id") or self.project.get("id") or self.project.get("slug"))
            if not project_id:
                raise RuntimeError("This result has no valid Modrinth project ID or slug")
            if self.project_type == "modpack":
                store = InstanceStore(self.instance_store_path)
                base_name = self.selection.get("instance_name") or self.project.get("title", "Modpack")
                existing = {item.name for item in store.instances}
                name = base_name
                counter = 2
                while name in existing:
                    name = f"{base_name} {counter}"
                    counter += 1
                self.instance = Instance(name=name, version=version, loader=loader or "fabric", ram_mb=4096)
                store.add(self.instance)
            instance_root = paths.instance_dir(self.instance.name)

            if self.project_type == "modpack":
                cache = instance_root / ".lumen" / "modpacks"
                self.status.emit("Downloading the selected modpack...")
                pack_file = catalog.download(
                    project_id, version, cache, loader=loader,
                    progress=lambda current, total: self.progress.emit(current, total),
                )
                self.status.emit("Installing modpack files in parallel...")
                result = install_modrinth_pack(
                    pack_file,
                    paths.minecraft_dir(),
                    instance_root,
                    self.status.emit,
                    self.progress.emit,
                )
                if result.loader == "fabric" and result.minecraft_version == "1.21.1":
                    mods_dir = instance_root / "mods"
                    if not any(mods_dir.glob("fabric-api-*.jar")):
                        try:
                            catalog.download(
                                "fabric-api", result.minecraft_version, mods_dir,
                                loader="fabric",
                                progress=lambda current, total: self.progress.emit(current, total),
                            )
                        except Exception as error:
                            self.status.emit(f"Fabric API was not added: {error}")
                    install_client_mod(mods_dir)

                store = InstanceStore(self.instance_store_path)
                updated = next(
                    (item for item in store.instances if item.name == self.instance.name),
                    None,
                )
                if updated is None:
                    raise RuntimeError("The selected instance was removed during installation")
                updated.version = result.minecraft_version
                updated.loader = result.loader
                updated.installed_version = result.installed_version
                store.save()
                self.instance.version = updated.version
                self.instance.loader = updated.loader
                self.instance.installed_version = updated.installed_version
                self.done.emit({
                    "message": f"Installed {result.name} • {result.loader} • Minecraft {result.minecraft_version}",
                    "instance": self.instance,
                })
                return

            effective_loader = loader or self.instance.loader
            if self.project_type == "mod":
                self.status.emit(f"Preparing {effective_loader} instance...")
                minecraft_launcher_lib.install.install_minecraft_version(
                    version, paths.minecraft_dir()
                )
                loader_ids = minecraft_launcher_lib.mod_loader.list_mod_loader()
                if effective_loader in {"vanilla", "minecraft"}:
                    self.instance.loader = "vanilla"
                    self.instance.version = version
                    self.instance.installed_version = None
                elif effective_loader in loader_ids:
                    if (
                        self.instance.loader != effective_loader
                        or self.instance.version != version
                        or not self.instance.installed_version
                    ):
                        java = ensure_java(
                            version, paths.minecraft_dir(), offline=False,
                            status=self.status.emit,
                        )
                        selected = minecraft_launcher_lib.mod_loader.get_mod_loader(
                            effective_loader
                        )
                        loader_version = selected.get_latest_loader_version(version)
                        self.instance.installed_version = selected.install(
                            version,
                            paths.minecraft_dir(),
                            loader_version=loader_version,
                            java=java,
                            callback={
                                "setStatus": self.status.emit,
                                "setProgress": lambda current: self.progress.emit(current, self._max[0]),
                                "setMax": self._set_max,
                            },
                        )
                        self.instance.loader = effective_loader
                        self.instance.version = version
                    store = InstanceStore(self.instance_store_path)
                    updated = next(
                        (item for item in store.instances if item.name == self.instance.name),
                        None,
                    )
                    if updated:
                        updated.version = self.instance.version
                        updated.loader = self.instance.loader
                        updated.installed_version = self.instance.installed_version
                        store.save()
                elif self.instance.version != version:
                    raise RuntimeError(
                        f"{effective_loader} is not a supported game loader; "
                        "choose Auto or a supported Modrinth loader."
                    )

                mods_dir = instance_root / "mods"
                mods_dir.mkdir(parents=True, exist_ok=True)
                if self.instance.loader == "fabric" and version == "1.21.1":
                    if not any(mods_dir.glob("fabric-api-*.jar")):
                        catalog.download(
                            "fabric-api", version, mods_dir, loader="fabric",
                            progress=lambda current, total: self.progress.emit(current, total),
                        )
                    install_client_mod(mods_dir)

            if self.project_type == "shader" and loader == "iris":
                if self.instance.loader not in {"fabric", "quilt", "neoforge"}:
                    raise RuntimeError(
                        "Iris shaders need a Fabric, Quilt, or NeoForge instance. "
                        "Select a compatible instance first."
                    )
                mods_dir = instance_root / "mods"
                mods_dir.mkdir(parents=True, exist_ok=True)
                if not any(mods_dir.glob("iris-*.jar")):
                    self.status.emit("Adding Iris to the selected instance...")
                    catalog.download(
                        "iris", version, mods_dir, loader=self.instance.loader,
                        progress=lambda current, total: self.progress.emit(current, total),
                    )

            folder = "shaderpacks" if self.project_type == "shader" else "mods"
            destination = instance_root / folder
            self.status.emit(f"Downloading to {self.instance.name}/{folder}...")
            output = catalog.download(
                project_id, version, destination, loader=loader,
                progress=lambda current, total: self.progress.emit(current, total),
            )
            if self.project_type == "shader" and loader == "optifine":
                message = f"Installed {output.name}; this instance also needs OptiFine."
            else:
                message = f"Installed {output.name}"
            self.done.emit({"message": message, "instance": self.instance if self.project_type == "mod" else None})
        except OSError as error:
            number = getattr(error, "winerror", None)
            details = f"Windows error {number}" if number is not None else type(error).__name__
            self.failed.emit(f"{details}: {error}")
        except Exception as error:
            self.failed.emit(str(error))


class CatalogTab(QWidget):
    def __init__(self, project_type: str, on_installed=None, parent=None):
        super().__init__(parent)
        self.project_type = project_type
        self.on_installed = on_installed
        self.catalog = ModrinthCatalog()
        self.results_data = []
        self.search_worker = None
        self.details_worker = None
        self.install_worker = None
        self.progress_dialog = None

        layout = QVBoxLayout(self)
        layout.addWidget(title_label(project_type.title() + " browser"))
        layout.addWidget(muted_label(
            "Search Modrinth. Double-click a result to choose an instance, version, and loader."
        ))

        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search Modrinth...")
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        self.search_button = QPushButton("SEARCH")
        self.search_button.clicked.connect(self.search)
        row.addWidget(self.search_button)
        layout.addLayout(row)

        self.results = QListWidget()
        self.results.setIconSize(QPixmap(48, 48).size())
        self.results.itemDoubleClicked.connect(self.open_details)
        layout.addWidget(self.results, 1)
        self.status = muted_label("Search Modrinth to browse compatible content.")
        layout.addWidget(self.status)

    def search(self):
        self.search_button.setEnabled(False)
        self.status.setText("Searching Modrinth...")
        self.search_worker = CatalogWorker(self.project_type, self.query.text().strip())
        self.search_worker.loaded.connect(self.set_results)
        self.search_worker.failed.connect(self.search_failed)
        self.search_worker.finished.connect(lambda: self.search_button.setEnabled(True))
        self.search_worker.start()

    def search_failed(self, error: str):
        self.status.setText(f"Search failed: {error}")

    def set_results(self, values: list):
        self.results_data = values
        self.results.clear()
        for value in values:
            item = QListWidgetItem(
                f'{value.get("title", value.get("project_id", "Unknown"))}\n'
                f'{value.get("description", "")[:110]}'
            )
            icon_data = value.get("_icon_bytes", b"")
            if icon_data:
                image = QImage.fromData(icon_data)
                if not image.isNull():
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
            item.setToolTip(value.get("description", ""))
            self.results.addItem(item)
        self.status.setText(f"{len(values)} results • double-click one for details")

    def open_details(self, item):
        row = self.results.row(item)
        if row < 0 or row >= len(self.results_data):
            return
        self.status.setText("Loading project details and screenshots...")
        self.details_worker = ProjectDetailsWorker(
            self.results_data[row]["project_id"]
        )
        self.details_worker.loaded.connect(self.show_details)
        self.details_worker.failed.connect(
            lambda message: self.status.setText(f"Could not open details: {message}")
        )
        self.details_worker.start()

    def show_details(self, project: dict, versions: list):
        store = InstanceStore(paths.config_path().parent / "instances.json")
        project["project_type"] = self.project_type
        dialog = ContentDetailsDialog(
            project, versions, store.instances, self.start_download, self
        )
        self.status.setText(f"Viewing {project.get('title', 'project')}")
        dialog.exec()

    def start_download(self, project: dict, selection: dict):
        store_path = paths.config_path().parent / "instances.json"
        store = InstanceStore(store_path)
        instance = next(
            (item for item in store.instances
             if item.name == selection.get("instance_name")),
            None,
        )
        if instance is None and self.project_type == "modpack":
            requested = selection.get("instance_name") or project.get("title", "New Modpack")
            instance = Instance(
                name=requested, version=selection.get("minecraft_version", "1.21.1"),
                loader=selection.get("loader") or "fabric", ram_mb=4096,
            )
            store.add(instance)
        if instance is None:
            QMessageBox.warning(self, "Instance missing", "Create or select an instance first.")
            return
        self.progress_dialog = CatalogProgressDialog(
            f"Installing {project.get('title', 'content')}", self
        )
        self.install_worker = CatalogInstallWorker(
            project,
            selection,
            self.project_type,
            instance,
            store_path,
        )
        self.install_worker.status.connect(self.progress_dialog.write)
        self.install_worker.progress.connect(self.progress_dialog.set_progress)
        self.install_worker.done.connect(self.install_succeeded)
        self.install_worker.failed.connect(self.install_failed)
        self.install_worker.start()
        self.progress_dialog.show()

    def install_succeeded(self, result: dict):
        message = result["message"]
        self.status.setText(message)
        if self.progress_dialog:
            self.progress_dialog.finish(message, success=True)
        if result.get("instance") and self.on_installed:
            self.on_installed(result["instance"])

    def install_failed(self, error: str):
        self.status.setText(f"Install failed: {error}")
        if self.progress_dialog:
            self.progress_dialog.finish(f"\nFAILED\n{error}", success=False)


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


class SkinsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = None
        self.pending_image = None
        self.skin_directory = paths.data_dir() / "skins"
        self.settings_path = paths.config_path().parent / "skin_models.json"

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(title_label("Local skins"))
        layout.addWidget(muted_label(
            "Choose a 64×64 PNG skin for your offline profile. "
            "In-game skin rendering is bundled with Lumen Fabric 1.21.1."
        ))

        card = QWidget()
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(18)
        card.setStyleSheet(
            "background:#13171c;border:1px solid #2c333c;border-radius:12px;"
        )

        self.preview = QLabel("Choose a skin image")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(220, 220)
        self.preview.setStyleSheet(
            "background:#0b0d10;border:1px solid #3d4652;border-radius:10px;"
        )
        card_layout.addWidget(self.preview)

        controls = QVBoxLayout()
        self.profile_label = QLabel("No offline account selected")
        self.profile_label.setObjectName("title")
        controls.addWidget(self.profile_label)

        model_row = QHBoxLayout()
        model_row.addWidget(muted_label("Player model"))
        self.model_box = QComboBox()
        self.model_box.addItem("Classic (wide)", "wide")
        self.model_box.addItem("Slim (Alex)", "slim")
        model_row.addWidget(self.model_box, 1)
        controls.addLayout(model_row)

        self.choose_button = QPushButton("CHOOSE PNG SKIN")
        self.choose_button.clicked.connect(self.choose_skin)
        controls.addWidget(self.choose_button)
        self.apply_button = QPushButton("APPLY TO OFFLINE ACCOUNT")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_skin)
        controls.addWidget(self.apply_button)
        self.clear_button = QPushButton("REMOVE LOCAL SKIN")
        self.clear_button.setObjectName("secondary")
        self.clear_button.clicked.connect(self.remove_skin)
        controls.addWidget(self.clear_button)
        self.status = muted_label("The skin is stored locally on this computer.")
        self.status.setWordWrap(True)
        controls.addWidget(self.status)
        controls.addStretch()
        card_layout.addLayout(controls, 1)

        layout.addWidget(card)
        layout.addStretch()
        self.set_profile(None)

    def _settings(self) -> dict:
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _skin_path(self):
        if not self.profile:
            return None
        return self.skin_directory / f"{self.profile.uuid}.png"

    def set_profile(self, profile):
        self.profile = profile
        self.pending_image = None
        self.apply_button.setEnabled(False)
        if not profile:
            self.profile_label.setText("No offline account selected")
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Add an offline account first")
            self.status.setText("Skins are saved per offline account.")
            return

        self.profile_label.setText(profile.username)
        model = self._settings().get(profile.uuid, "wide")
        index = self.model_box.findData(model)
        self.model_box.setCurrentIndex(index if index >= 0 else 0)
        path = self._skin_path()
        if path and path.is_file():
            self._show_image(QImage(str(path)))
            self.status.setText(f"Local skin ready for {profile.username}.")
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("No skin selected")
            self.status.setText("Choose a 64×64 PNG skin to use with this profile.")

    def _show_image(self, image: QImage):
        pixmap = QPixmap.fromImage(image)
        self.preview.setPixmap(pixmap.scaled(
            192, 192, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        ))
        self.preview.setText("")

    def choose_skin(self):
        if not self.profile:
            QMessageBox.information(self, "Offline account needed", "Add an offline account first.")
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose a Minecraft skin", "", "PNG skin images (*.png)"
        )
        if not filename:
            return
        image = QImage(filename)
        if image.isNull() or image.width() != 64 or image.height() != 64:
            QMessageBox.warning(
                self, "Unsupported skin image",
                "Choose a valid 64×64 PNG skin image.",
            )
            return
        self.pending_image = image
        self._show_image(image)
        self.apply_button.setEnabled(True)
        self.status.setText(Path(filename).name + " is ready to apply.")

    def apply_skin(self):
        if not self.profile or self.pending_image is None:
            return
        destination = self._skin_path()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not self.pending_image.save(str(destination), "PNG"):
            self.status.setText("Could not save the skin image.")
            return
        values = self._settings()
        values[self.profile.uuid] = self.model_box.currentData()
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(values, indent=2), encoding="utf-8"
        )
        self.pending_image = None
        self.apply_button.setEnabled(False)
        self.status.setText(
            "Skin applied locally. Launch a Fabric 1.21.1 instance to see it in-game."
        )

    def remove_skin(self):
        if not self.profile:
            return
        path = self._skin_path()
        if path and path.exists():
            answer = QMessageBox.question(
                self, "Remove local skin",
                f"Remove the saved skin for {self.profile.username}?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            path.unlink(missing_ok=True)
        values = self._settings()
        values.pop(self.profile.uuid, None)
        self.settings_path.write_text(json.dumps(values, indent=2), encoding="utf-8")
        self.set_profile(self.profile)
        self.status.setText("Local skin removed.")

    def jvm_arguments(self, profile) -> list[str]:
        path = paths.data_dir() / "skins" / f"{profile.uuid}.png"
        if not path.is_file():
            return []
        model = self._settings().get(profile.uuid, "wide")
        return [
            f"-Dlumen.skin.path={path}",
            f"-Dlumen.skin.uuid={profile.uuid}",
            f"-Dlumen.skin.model={model}",
        ]


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
        icon_path = resource_path("assets/lumen-app.ico")
        if icon_path.is_file():
            brand_icon = QLabel()
            brand_icon.setPixmap(QIcon(str(icon_path)).pixmap(38, 38))
            header.addWidget(brand_icon)
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

        self.instances_tab = InstancesTab(self.select_instance)
        self.mods_tab = CatalogTab("mod", self.catalog_installed)
        self.shaders_tab = CatalogTab("shader", self.catalog_installed)
        self.modpacks_tab = CatalogTab("modpack", self.catalog_installed)
        self.servers_tab = ServersTab()
        self.skins_tab = SkinsTab()
        self.settings_tab = SettingsTab()

        shell = QHBoxLayout()
        shell.setSpacing(14)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(178)
        self.page_stack = QStackedWidget()
        pages = [
            ("HOME", self.home_tab()),
            ("INSTANCES", self.instances_tab),
            ("MODS", self.mods_tab),
            ("SHADERS", self.shaders_tab),
            ("MODPACKS", self.modpacks_tab),
            ("SERVERS", self.servers_tab),
            ("SKINS", self.skins_tab),
            ("SETTINGS", self.settings_tab),
        ]
        for label, page in pages:
            self.navigation.addItem(QListWidgetItem(label))
            self.page_stack.addWidget(page)
        self.navigation.currentRowChanged.connect(self.page_stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        shell.addWidget(self.navigation)
        shell.addWidget(self.page_stack, 1)
        outer.addLayout(shell, 1)

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
        self.home_version.currentTextChanged.connect(self.home_instance_changed)
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

    def refresh_instances(self, preferred_name=None):
        self.instances_tab.refresh()
        store = self.instances_tab.store
        self.home_version.blockSignals(True)
        self.home_version.clear()
        for instance in store.instances:
            self.home_version.addItem(instance.name)
        if not store.instances:
            self.home_version.addItem("No instances")
            self.current_instance = None
        else:
            wanted = preferred_name or (
                self.current_instance.name if self.current_instance else None
            )
            index = next(
                (i for i, instance in enumerate(store.instances) if instance.name == wanted),
                0,
            )
            self.home_version.setCurrentIndex(index)
            self.current_instance = store.instances[index]
        self.home_version.blockSignals(False)

    def home_instance_changed(self, name: str):
        store = InstanceStore(paths.config_path().parent / "instances.json")
        self.current_instance = next(
            (item for item in store.instances if item.name == name), None
        )

    def select_instance(self, instance):
        self.current_instance = instance
        index = self.home_version.findText(instance.name)
        if index >= 0:
            self.home_version.setCurrentIndex(index)

    def catalog_installed(self, instance):
        self.refresh_instances(preferred_name=instance.name)
        self.log.appendPlainText(
            f"Updated instance {instance.name}: {instance.loader} {instance.version}"
        )

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
            profile = None
            self.account_button.setText("＋  ADD OFFLINE ACCOUNT")
        if hasattr(self, "skins_tab"):
            self.skins_tab.set_profile(profile)

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
                self.current_instance.loader != "vanilla"
                and not self.current_instance.installed_version
            ):
                raise RuntimeError(
                    "Install this instance first so its real loader version is selected"
                )
            version = (
                self.current_instance.installed_version
                or self.current_instance.version
            )
            instance_root = paths.instance_dir(self.current_instance.name)
            jvm = [
                f"-Xmx{self.current_instance.ram_mb}M",
                f"-Xms{min(1024, self.current_instance.ram_mb)}M",
            ]
            jvm.extend(self.skins_tab.jvm_arguments(profile))
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
    icon_path = resource_path("assets/lumen-app.ico")
    app_icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
    app.setWindowIcon(app_icon)

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
    splash.setWindowIcon(app_icon)
    splash.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    splash.show()
    app.processEvents()

    window = LumenWindow()
    window.setWindowIcon(app_icon)

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
