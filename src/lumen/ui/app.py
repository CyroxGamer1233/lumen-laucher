"""Minimal PySide6 front-end. All logic lives in the modules above; this only wires buttons."""
from __future__ import annotations
import sys
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QLabel, QMainWindow, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)
from .. import paths, config, logging_setup
from ..auth.offline import offline_account
from ..auth.store import AccountStore


class LaunchWorker(QThread):
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, settings: config.Settings, offline: bool):
        super().__init__()
        self.settings, self.offline = settings, offline

    def run(self) -> None:
        try:
            from ..launch import service, process
            mc_dir = paths.minecraft_dir()
            game_dir = paths.instance_dir(f"{self.settings.loader}-{self.settings.mc_version}")
            vid = service.prepare(self.settings.mc_version, self.settings.loader, mc_dir, self.status.emit)
            if not self.offline:
                raise RuntimeError("Use 'lumen login' once, then tick Offline or extend this worker with refresh().")
            acct = offline_account(self.settings.offline_username)
            cmd = service.build_command(vid, acct, self.settings, mc_dir, game_dir)
            self.status.emit("Launching…")
            process.launch(cmd, game_dir, paths.log_dir() / "game.log").wait()
            self.status.emit("Game closed")
        except Exception as e:
            self.failed.emit(str(e))


class Main(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lumen Launcher")
        self.settings = config.load(paths.config_path())
        self.store = AccountStore(paths.accounts_index_path())
        box = QVBoxLayout()
        self.version = QComboBox()
        self.version.addItems(["1.21.1", "1.20.1"])
        self.version.setCurrentText(self.settings.mc_version)
        self.play = QPushButton("Play (offline profile)")
        self.play.setEnabled(self.store.has_verified_ownership())
        self.log = QPlainTextEdit(readOnly=True)
        for w in (QLabel("Minecraft version"), self.version, self.play, self.log):
            box.addWidget(w)
        host = QWidget()
        host.setLayout(box)
        self.setCentralWidget(host)
        self.play.clicked.connect(self.start)

    def start(self) -> None:
        self.settings.mc_version = self.version.currentText()
        config.save(self.settings, paths.config_path())
        self.play.setEnabled(False)
        self.w = LaunchWorker(self.settings, offline=True)
        self.w.status.connect(self.log.appendPlainText)
        self.w.failed.connect(lambda m: self.log.appendPlainText(f"ERROR: {m}"))
        self.w.finished.connect(lambda: self.play.setEnabled(True))
        self.w.start()


def main() -> int:
    logging_setup.setup(paths.log_dir())
    app = QApplication(sys.argv)
    win = Main()
    win.resize(520, 420)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
