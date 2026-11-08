from __future__ import annotations

from pathlib import Path

import minecraft_launcher_lib
from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from lumen import paths
from lumen.instances import Instance, InstanceStore
from lumen.client_mod import install_client_mod
from lumen.catalog import ModrinthCatalog

CLIENT_MOD_MINECRAFT_VERSION = "1.21.1"


class InstanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New instance")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("My Fabric Profile")
        self.version = QLineEdit("1.21.1")
        self.loader = QComboBox()
        self.loader.addItems(["vanilla", "fabric", "forge"])
        self.ram = QSpinBox()
        self.ram.setRange(1024, 32768)
        self.ram.setSingleStep(512)
        self.ram.setValue(4096)
        form.addRow("Instance name", self.name)
        form.addRow("Minecraft version", self.version)
        form.addRow("Loader", self.loader)
        form.addRow("RAM", self.ram)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        if not self.name.text().strip() or not self.version.text().strip():
            QMessageBox.warning(self, "Incomplete", "Name and version are required")
            return
        self.instance = Instance(
            self.name.text().strip(),
            self.version.text().strip(),
            self.loader.currentText(),
            self.ram.value(),
        )
        super().accept()


class InstanceInstallWorker(QThread):
    status = Signal(str)
    done = Signal()
    failed = Signal(str)

    def __init__(self, instance: Instance, directory: Path):
        super().__init__()
        self.instance, self.directory = instance, directory

    def run(self):
        try:
            callback = {
                "setStatus": self.status.emit,
                "setProgress": lambda _value: None,
                "setMax": lambda _value: None,
            }
            minecraft_launcher_lib.install.install_minecraft_version(
                self.instance.version, self.directory, callback=callback
            )
            if self.instance.loader == "fabric":
                loader_version = minecraft_launcher_lib.fabric.get_latest_loader_version()
                minecraft_launcher_lib.fabric.install_fabric(
                    self.instance.version,
                    self.directory,
                    loader_version=loader_version,
                    callback=callback,
                )
                self.instance.installed_version = (
                    f"fabric-loader-{loader_version}-{self.instance.version}"
                )
            elif self.instance.loader == "forge":
                forge_version = minecraft_launcher_lib.forge.find_forge_version(
                    self.instance.version
                )
                if not forge_version:
                    raise RuntimeError("No Forge build is available for this version")
                minecraft_launcher_lib.forge.install_forge_version(
                    forge_version, self.directory, callback=callback
                )
                self.instance.installed_version = (
                    minecraft_launcher_lib.forge.forge_to_installed_version(
                        forge_version
                    )
                )
            instance_root = paths.data_dir() / "instances" / self.instance.name
            if self.instance.loader == "fabric":
                mods_directory = instance_root / "mods"
                fabric_api = ModrinthCatalog().download(
                    "fabric-api",
                    self.instance.version,
                    mods_directory,
                    loader="fabric",
                )
                self.status.emit(f"Fabric API installed: {fabric_api.name}")

                if self.instance.version == CLIENT_MOD_MINECRAFT_VERSION:
                    client_mod = install_client_mod(mods_directory)
                    if client_mod:
                        self.status.emit(f"Client mod installed: {client_mod.name}")
                    else:
                        self.status.emit(
                            "Client mod not found; build client-mod first"
                        )
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
        self.list.currentRowChanged.connect(self.instance_selected)
        row.addWidget(self.list, 1)

        actions = QVBoxLayout()
        new_button = QPushButton("+ NEW INSTANCE")
        new_button.clicked.connect(self.new_instance)
        actions.addWidget(new_button)
        self.install_button = QPushButton("DOWNLOAD / INSTALL")
        self.install_button.clicked.connect(self.install_selected)
        actions.addWidget(self.install_button)
        self.play_button = QPushButton("PLAY INSTANCE")
        self.play_button.clicked.connect(self.play_selected)
        actions.addWidget(self.play_button)
        self.open_button = QPushButton("OPEN DIRECTORY")
        self.open_button.clicked.connect(self.open_directory)
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
        self.list.clear()
        for instance in self.store.instances:
            self.list.addItem(QListWidgetItem(
                f"{instance.name}  •  {instance.version}  •  {instance.loader}"
            ))

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
                f"Launch ID: {installed}"
            )
            if self.on_selected:
                self.on_selected(instance)

    def new_instance(self):
        dialog = InstanceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.add(dialog.instance)
            self.refresh()
            self.list.setCurrentRow(len(self.store.instances) - 1)

    def install_selected(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        self.install_button.setEnabled(False)
        self.status.setText("Installing...")
        self.worker = InstanceInstallWorker(instance, paths.minecraft_dir())
        self.worker.status.connect(self.status.setText)
        self.worker.done.connect(lambda: self.install_finished(instance))
        self.worker.failed.connect(self.install_failed)
        self.worker.start()

    def install_finished(self, instance):
        self.install_button.setEnabled(True)
        self.status.setText(f"{instance.name} is ready")
        self.store.save()

    def install_failed(self, error: str):
        self.install_button.setEnabled(True)
        self.status.setText(error)

    def open_directory(self):
        instance = self.current()
        if not instance:
            self.status.setText("Select an instance first")
            return
        directory = paths.data_dir() / "instances" / instance.name
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def play_selected(self):
        instance = self.current()
        if instance and self.on_selected:
            self.on_selected(instance)
            self.status.setText("Selected. Use Home → PLAY OFFLINE.")
