from __future__ import annotations

import re
import shutil
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

import minecraft_launcher_lib
from PySide6.QtCore import QThread, QUrl, Signal, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QStyle, QVBoxLayout, QWidget,
)

from lumen import paths
from lumen.instances import Instance, InstanceStore
from lumen.client_mod import install_client_mod
from lumen.catalog import ModrinthCatalog
from lumen.java_runtime import ensure_java
from lumen.paths import instance_dir

CLIENT_MOD_MINECRAFT_VERSION = "1.21.1"


class InstallLogDialog(QDialog):
    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Installing {instance.name}")
        self.setMinimumSize(700, 500)
        self.resize(760, 540)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        self.title = QLabel(
            f"{instance.name}  •  Minecraft {instance.version}  •  {instance.loader}"
        )
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.phase = QLabel("Preparing a secure installation...")
        self.phase.setObjectName("muted")
        layout.addWidget(self.phase)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFormat("Preparing…")
        self.progress.setFixedHeight(20)
        layout.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Installation steps and download status will appear here.")
        self.log.setMaximumBlockCount(2000)
        self.log.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace;")
        layout.addWidget(self.log, 1)

        self.close_button = QPushButton("INSTALLING…")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

    def write(self, message: str):
        self.log.appendPlainText(message)

    def set_phase(self, message: str):
        self.phase.setText(message)

    def set_progress(self, current: int, maximum: int):
        if maximum <= 0:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Downloading…")
            return
        maximum = max(1, int(maximum))
        current = min(max(0, int(current)), maximum)
        self.progress.setRange(0, maximum)
        self.progress.setValue(current)
        self.progress.setFormat("%p%")

    def finished(self, message: str, success: bool):
        self.write(message)
        self.phase.setText("Installation complete" if success else "Installation stopped")
        if success:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.progress.setFormat("Ready to play")
            self.close_button.setText("DONE")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setFormat("See the log for details")
            self.close_button.setText("CLOSE")
        self.close_button.setEnabled(True)


class InstanceDialog(QDialog):
    def __init__(self, instance=None, parent=None):
        super().__init__(parent)
        self.instance = instance
        self.setWindowTitle("Edit instance" if instance else "New instance")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("My Fabric Profile")
        self.version = QLineEdit("1.21.1")
        self.loader = QComboBox()
        self.loader.addItems(["vanilla", "fabric", "forge", "neoforge", "quilt"])
        self.ram = QSpinBox()
        self.ram.setRange(1024, 32768)
        self.ram.setSingleStep(512)
        self.ram.setValue(4096)
        self.path = QLineEdit()
        self.path.setPlaceholderText("Default Lumen instance folder")
        browse = QPushButton("BROWSE")
        browse.clicked.connect(self.browse_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)
        if instance:
            self.name.setText(instance.name)
            self.version.setText(instance.version)
            self.loader.setCurrentText(instance.loader)
            self.ram.setValue(instance.ram_mb)
            self.path.setText(getattr(instance, "path", "") or "")
        form.addRow("Instance name", self.name)
        form.addRow("Minecraft version", self.version)
        form.addRow("Loader", self.loader)
        form.addRow("RAM (MB)", self.ram)
        form.addRow("Instance folder", path_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def browse_path(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose instance folder")
        if selected:
            self.path.setText(selected)

    def accept(self):
        name = self.name.text().strip()
        if not name or not self.version.text().strip():
            QMessageBox.warning(self, "Incomplete", "Name and version are required")
            return
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}
        if (
            not re.fullmatch(r"[A-Za-z0-9 _.-]{1,48}", name)
            or name.endswith((".", " "))
            or name.split(".", 1)[0].upper() in reserved
        ):
            QMessageBox.warning(
                self, "Invalid name",
                "Use up to 48 letters, numbers, spaces, dots, dashes, or underscores. "
                "Avoid Windows reserved names.",
            )
            return
        self.instance = Instance(
            name=name,
            version=self.version.text().strip(),
            loader=self.loader.currentText(),
            ram_mb=self.ram.value(),
            installed_version=(self.instance.installed_version if self.instance else None),
            path=self.path.text().strip() or None,
        )
        super().accept()


class InstanceInstallWorker(QThread):
    status = Signal(str)
    progress = Signal(int, int)
    done = Signal()
    failed = Signal(str)

    def __init__(self, instance: Instance, directory: Path):
        super().__init__()
        self.instance, self.directory = instance, directory

    def run(self):
        try:
            maximum = [0]

            def set_max(value):
                maximum[0] = max(0, int(value))
                self.progress.emit(0, maximum[0])

            def set_progress(value):
                self.progress.emit(max(0, int(value)), maximum[0])

            callback = {
                "setStatus": self.status.emit,
                "setProgress": set_progress,
                "setMax": set_max,
            }
            minecraft_launcher_lib.install.install_minecraft_version(
                self.instance.version, self.directory, callback=callback
            )

            if self.instance.loader == "vanilla":
                self.instance.installed_version = None
            else:
                self.status.emit(f"Preparing Java for {self.instance.loader}...")
                java_executable = ensure_java(
                    self.instance.version,
                    self.directory,
                    offline=False,
                    status=self.status.emit,
                )
                loader = minecraft_launcher_lib.mod_loader.get_mod_loader(
                    self.instance.loader
                )
                loader_version = loader.get_latest_loader_version(self.instance.version)
                self.status.emit(
                    f"Installing {loader.get_name()} {loader_version}..."
                )
                self.instance.installed_version = loader.install(
                    self.instance.version,
                    self.directory,
                    loader_version=loader_version,
                    callback=callback,
                    java=java_executable,
                )

            if self.instance.loader == "fabric":
                mods_directory = Path(getattr(self.instance, "path", "") or instance_dir(self.instance.name)) / "mods"
                mods_directory.mkdir(parents=True, exist_ok=True)
                if not any(mods_directory.glob("fabric-api-*.jar")):
                    self.status.emit("Downloading Fabric API...")
                    fabric_api = ModrinthCatalog().download(
                        "fabric-api",
                        self.instance.version,
                        mods_directory,
                        loader="fabric",
                        progress=lambda current, total: self.progress.emit(current, total),
                    )
                    self.status.emit(f"Fabric API installed: {fabric_api.name}")

                if self.instance.version == CLIENT_MOD_MINECRAFT_VERSION:
                    client_mod = install_client_mod(mods_directory)
                    if client_mod:
                        self.status.emit(f"Client mod installed: {client_mod.name}")
                    else:
                        self.status.emit("Client mod not found; build client-mod first")
                else:
                    self.status.emit(
                        f"Client mod skipped: supports only {CLIENT_MOD_MINECRAFT_VERSION}"
                    )
            self.done.emit()
        except Exception as error:
            self.failed.emit(str(error))


class InstancesTab(QWidget):
    selected = Signal(object)

    def __init__(self, on_selected=None, parent=None):
        super().__init__(parent)
        self.store = InstanceStore(
            paths.config_path().parent / "instances.json"
        )
        self.on_selected = on_selected
        self.worker = None
        self.install_log = None

        layout = QVBoxLayout(self)
        title = QLabel("Instances")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel(
            "Create a named profile with its own version, loader, and RAM."
        )
        hint.setObjectName("muted")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setIconSize(QSize(32, 32))
        self.list.itemDoubleClicked.connect(lambda _item: self.toggle_mods())
        self.list.currentRowChanged.connect(self.instance_selected)
        row.addWidget(self.list, 1)

        actions = QVBoxLayout()
        new_button = QPushButton("+ NEW INSTANCE")
        new_button.clicked.connect(self.new_instance)
        actions.addWidget(new_button)
        self.edit_button = QPushButton("EDIT INSTANCE")
        self.edit_button.clicked.connect(self.edit_selected)
        actions.addWidget(self.edit_button)
        self.install_button = QPushButton("DOWNLOAD / INSTALL")
        self.install_button.clicked.connect(self.install_selected)
        actions.addWidget(self.install_button)
        self.play_button = QPushButton("PLAY INSTANCE")
        self.play_button.clicked.connect(self.play_selected)
        actions.addWidget(self.play_button)
        self.open_button = QPushButton("OPEN DIRECTORY")
        self.open_button.clicked.connect(self.open_directory)
        self.select_button = QPushButton("SELECT INSTANCE")
        self.select_button.clicked.connect(self.play_selected)
        actions.addWidget(self.select_button)
        self.delete_button = QPushButton("DELETE INSTANCE")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_button)
        for button in (new_button, self.edit_button, self.install_button, self.play_button, self.open_button, self.select_button, self.delete_button):
            button.setObjectName("primary")
        actions.addWidget(self.open_button)
        actions.addStretch()
        row.addLayout(actions)
        layout.addLayout(row)

        self.details = QLabel("Select an instance")
        self.details.setObjectName("muted")
        layout.addWidget(self.details)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self):
        self.store = InstanceStore(self.store.path)
        self.list.clear()
        instance_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        for instance in self.store.instances:
            root = Path(getattr(instance, "path", "") or instance_dir(instance.name))
            mods = root / "mods"
            mod_count = len(list(mods.glob("*.jar"))) + len(list(mods.glob("*.jar.disabled")))
            item = QListWidgetItem(
                instance_icon,
                f"  {instance.name}  •  {instance.version}  •  {instance.loader}  •  {mod_count} mods  •  {self._format_playtime(instance.playtime_seconds)}",
            )
            item.setToolTip("Double-click to enable or disable all mods in this instance")
            self.list.addItem(item)

    def current(self):
        row = self.list.currentRow()
        return self.store.instances[row] if 0 <= row < len(self.store.instances) else None

    def instance_selected(self, _row):
        instance = self.current()
        if instance:
            installed = instance.installed_version or "not installed"
            self.details.setText(
                f"{instance.name}\\nMinecraft {instance.version} • "
                f"{instance.loader} • {instance.ram_mb} MB RAM\\n"
                f"Playtime: {self._format_playtime(instance.playtime_seconds)} • Launch ID: {installed}"
            )
            if self.on_selected:
                self.on_selected(instance)

    def new_instance(self):
        dialog = InstanceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.add(dialog.instance)
            self.refresh()
            self.list.setCurrentRow(len(self.store.instances) - 1)

    def edit_selected(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        dialog = InstanceDialog(instance, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.store.add(dialog.instance)
        self.refresh()
        self.list.setCurrentRow(next(
            (index for index, item in enumerate(self.store.instances)
             if item.name == dialog.instance.name), 0
        ))
        self.status.setText("Instance settings saved")

    def toggle_mods(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        mods = Path(getattr(instance, "path", "") or instance_dir(instance.name)) / "mods"
        mods.mkdir(parents=True, exist_ok=True)
        jars = list(mods.glob("*.jar"))
        disabled = list(mods.glob("*.jar.disabled"))
        if jars:
            for jar in jars:
                jar.rename(jar.with_name(jar.name + ".disabled"))
            self.status.setText(f"Disabled {len(jars)} mods in {instance.name}")
        elif disabled:
            for jar in disabled:
                jar.rename(jar.with_suffix(""))
            self.status.setText(f"Enabled {len(disabled)} mods in {instance.name}")
        else:
            self.status.setText("No mods installed in this instance")
        self.refresh()
        self.list.setCurrentRow(next((n for n, item in enumerate(self.store.instances)
                                      if item.name == instance.name), -1))

    @staticmethod
    def _format_playtime(seconds):
        seconds = max(0, int(seconds or 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m"

    def delete_selected(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        answer = QMessageBox.question(
            self, "Delete instance",
            f"Delete '{instance.name}' and its local files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        folder = Path(getattr(instance, "path", "") or instance_dir(instance.name))
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        self.store.instances = [item for item in self.store.instances if item.name != instance.name]
        self.store.save()
        self.refresh()
        self.status.setText(f"Deleted {instance.name}")

    def install_selected(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        self.install_button.setEnabled(False)
        self.status.setText("Installing...")
        self.install_log = InstallLogDialog(instance, self)
        self.install_log.show()
        self.worker = InstanceInstallWorker(instance, paths.minecraft_dir())
        self.worker.status.connect(self.status.setText)
        self.worker.status.connect(self.install_log.set_phase)
        self.worker.status.connect(self.install_log.write)
        self.worker.progress.connect(self.install_log.set_progress)
        self.worker.done.connect(lambda: self.install_finished(instance))
        self.worker.failed.connect(self.install_failed)
        self.worker.start()

    def install_finished(self, instance):
        self.install_button.setEnabled(True)
        self.status.setText(
            f"{instance.name} is ready: {instance.installed_version or instance.version}"
        )
        self.store.save()
        if self.install_log:
            self.install_log.finished(
                f"\nCOMPLETE\nLaunch ID: "
                f"{instance.installed_version or instance.version}",
                success=True,
            )

    def install_failed(self, error: str):
        self.install_button.setEnabled(True)
        self.status.setText(error)
        if self.install_log:
            self.install_log.finished(f"\nFAILED\n{error}", success=False)

    def open_directory(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        directory = Path(getattr(instance, "path", "") or instance_dir(instance.name))
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def play_selected(self):
        instance = self.current()
        if instance and self.on_selected:
            self.on_selected(instance)
            self.status.setText("Selected. Use Home → PLAY OFFLINE.")
