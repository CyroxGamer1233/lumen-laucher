from __future__ import annotations

import sys
from pathlib import Path

import minecraft_launcher_lib
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget
)

from lumen import logging_setup, paths
from lumen.assets import AssetDownloader
from lumen.offline_launcher import OfflineLauncher
from lumen.offline_profiles import OfflineProfileDB


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
        self.tabs.addTab(self.versions_tab(), "Versions")
        for name in ("Mods", "Shaders", "Modpacks", "Servers", "Settings"):
            self.tabs.addTab(self.placeholder_tab(name), name)
        outer.addWidget(self.tabs)

        self.refresh_account()
        self.load_local_versions()

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
        grid.addWidget(QLabel("Minecraft version"), 0, 0)
        self.home_version = QComboBox()
        self.home_version.setEditable(True)
        self.home_version.addItem("1.21.1")
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

    def load_local_versions(self):
        self.refresh_installed()
        worker = VersionWorker(self.minecraft_dir)
        worker.loaded.connect(self.set_versions)
        worker.start()
        self.version_worker = worker

    def set_versions(self, versions: list):
        for box in (self.version_box, self.home_version):
            current = box.currentText()
            box.clear()
            box.addItems(versions or ["1.21.1"])
            if current:
                box.setCurrentText(current)

    def refresh_installed(self):
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
            version = self.home_version.currentText().strip()
            launcher = OfflineLauncher(self.minecraft_dir, self.profile_db)
            launcher.launch(version, profile=profile, output=self.log.appendPlainText)
            self.log.appendPlainText(f"Launching {version} as {profile.username}...")
        except Exception as error:
            QMessageBox.warning(self, "Cannot launch offline", str(error))


def main() -> int:
    logging_setup.setup(paths.log_dir())
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
