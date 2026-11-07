"""PySide6 front-end. Logic lives in the modules above; this only wires widgets to them."""
from __future__ import annotations

import logging
import sys
import webbrowser

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, config, logging_setup, paths, session

log = logging.getLogger("lumen.ui")


class SignInWorker(QThread):
    code = Signal(str, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, settings: config.Settings):
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        try:
            acct = session.sign_in(self.settings, lambda c, u: self.code.emit(c, u))
            self.done.emit(acct.username)
        except Exception as e:
            log.exception("sign-in failed")
            self.failed.emit(str(e))


class LaunchWorker(QThread):
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, settings: config.Settings, offline: bool, performance: bool, force: bool):
        super().__init__()
        self.settings, self.offline, self.performance, self.force = settings, offline, performance, force

    def run(self) -> None:
        try:
            from ..launch import process, service
            from ..launch.localcheck import verify_local_install
            from ..mods import provision
            from ..mods.manifest import detect_conflicts, scan_folder
            s, emit = self.settings, self.status.emit
            mc_dir = paths.minecraft_dir()
            game_dir = paths.instance_dir(f"{s.loader}-{s.mc_version}")

            # Offline sessions are fully local: no sign-in, keystore, downloads or network calls.
            acct = session.get_offline_account(s) if self.offline else None
            if self.offline:
                emit(f"Offline profile {acct.username}: checking local files only...")
            else:
                emit("Installing game files (the first run downloads about 1 GB)...")
            version_id = service.prepare(s.mc_version, s.loader, mc_dir, emit,
                                         offline=self.offline, loader_version=s.loader_version)
            if self.offline:
                missing = verify_local_install(mc_dir, version_id)
                if missing:
                    self.failed.emit(f"{len(missing)} game file(s) are missing (first: {missing[0]}). "
                                     "Run one online launch first or copy a populated Minecraft folder.")
                    return

            if s.loader == "fabric":
                mods = game_dir / "mods"
                provision.prepare_mods(mods, s.mc_version, self.performance, emit, offline=self.offline)
                errors = [i for i in detect_conflicts(scan_folder(mods), s.mc_version) if i.severity == "error"]
                for i in errors:
                    emit(f"[mod problem] {i.mod_id}: {i.message}")
                if errors and not self.force:
                    self.failed.emit("Mod problems found (see log). Fix them or tick 'Launch anyway'.")
                    return

            if acct is None:
                emit("Signing in...")
                acct = session.get_account(s, False)
            cmd = service.build_command(version_id, acct, s, mc_dir, game_dir,
                                        offline=self.offline, on_status=emit)
            emit(f"Launching as {acct.username}...")
            proc = process.launch(cmd, game_dir, paths.log_dir() / "game.log")
            code = proc.wait()
            emit(f"Game closed (exit code {code}). Logs: {paths.log_dir()}")
        except Exception as e:
            log.exception("launch failed")
            self.failed.emit(str(e))


class Main(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Lumen Launcher {__version__}")
        self.settings = config.load(paths.config_path())
        self.store = session.store()
        self.worker: QThread | None = None

        self.account_label = QLabel()
        self.sign_in_btn = QPushButton("Sign in with Microsoft")
        self.sign_out_btn = QPushButton("Sign out")
        self.client_id = QLineEdit(self.settings.ms_client_id)
        self.client_id.setPlaceholderText("Azure app client ID (one-time setup)")
        self.version = QComboBox()
        self.version.setEditable(True)
        self.version.addItems(["1.21.1", "1.20.1", "1.21.4"])
        self.version.setCurrentText(self.settings.mc_version)
        self.loader = QComboBox()
        self.loader.addItems(["fabric", "forge", "vanilla"])
        self.loader.setCurrentText(self.settings.loader)
        self.profile = QComboBox()
        self.profile.addItems(["low_end", "balanced", "high_end"])
        self.profile.setCurrentText(self.settings.jvm_profile)
        self.ram = QSpinBox()
        self.ram.setRange(0, 32768)
        self.ram.setSingleStep(512)
        self.ram.setSuffix(" MB")
        self.ram.setSpecialValueText("Auto")
        self.ram.setValue(self.settings.ram_mb or 0)
        self.perf = QCheckBox("Install performance mods (Sodium, Lithium, ...)")
        self.perf.setChecked(self.settings.mod_profile == "performance")
        self.offline = QCheckBox("Offline profile (local only: no sign-in, no network)")
        self.force = QCheckBox("Launch anyway if mod check fails")
        self.play = QPushButton("Play")
        self.log = QPlainTextEdit(readOnly=True)

        form = QFormLayout()
        form.addRow("Azure client ID", self.client_id)
        form.addRow("Minecraft version", self.version)
        form.addRow("Loader", self.loader)
        form.addRow("JVM profile", self.profile)
        form.addRow("Memory", self.ram)
        row = QHBoxLayout()
        row.addWidget(self.account_label, 1)
        row.addWidget(self.sign_in_btn)
        row.addWidget(self.sign_out_btn)
        box = QVBoxLayout()
        box.addLayout(row)
        box.addLayout(form)
        for w in (self.perf, self.offline, self.force, self.play, self.log):
            box.addWidget(w)
        host = QWidget()
        host.setLayout(box)
        self.setCentralWidget(host)

        self.sign_in_btn.clicked.connect(self.start_sign_in)
        self.sign_out_btn.clicked.connect(self.sign_out)
        self.play.clicked.connect(self.start_play)
        self.refresh_account()

    def say(self, text: str) -> None:
        self.log.appendPlainText(text)

    def refresh_account(self) -> None:
        accounts = self.store.list_accounts()
        names = ", ".join(a["username"] for a in accounts.values())
        self.account_label.setText(f"Signed in: {names}" if names else "Not signed in")
        self.sign_out_btn.setEnabled(bool(accounts))

    def save_settings(self) -> None:
        s = self.settings
        s.ms_client_id = self.client_id.text()
        s.mc_version = self.version.currentText().strip()
        s.loader = self.loader.currentText()
        s.jvm_profile = self.profile.currentText()
        s.ram_mb = self.ram.value() or None
        s.mod_profile = "performance" if self.perf.isChecked() else "minimal"
        config.save(s, paths.config_path())

    def busy(self, on: bool) -> None:
        for w in (self.play, self.sign_in_btn):
            w.setEnabled(not on)

    def start_sign_in(self) -> None:
        self.save_settings()
        if not session.client_id(self.settings):
            QMessageBox.information(self, "Client ID needed",
                                    "Enter your Azure app's client ID first (see the user guide).")
            return
        self.busy(True)
        w = SignInWorker(self.settings)
        w.code.connect(self.show_code)
        w.done.connect(self.sign_in_done)
        w.failed.connect(self.on_failed)
        w.finished.connect(lambda: self.busy(False))
        self.worker = w
        w.start()

    def show_code(self, code: str, url: str) -> None:
        QApplication.clipboard().setText(code)
        self.say(f"Open {url} and enter code {code} (copied to clipboard).")
        webbrowser.open(url)

    def sign_in_done(self, name: str) -> None:
        self.say(f"Signed in as {name}.")
        self.refresh_account()

    def sign_out(self) -> None:
        for uuid in list(self.store.list_accounts()):
            self.store.remove(uuid)
        self.refresh_account()
        self.say("Signed out.")

    def on_failed(self, msg: str) -> None:
        self.say(f"ERROR: {msg}")

    def start_play(self) -> None:
        self.save_settings()
        if not self.offline.isChecked() and not self.store.list_accounts():
            QMessageBox.information(self, "Sign in first", "Sign in with Microsoft before playing.")
            return
        self.busy(True)
        w = LaunchWorker(self.settings, self.offline.isChecked(), self.perf.isChecked(), self.force.isChecked())
        w.status.connect(self.say)
        w.failed.connect(self.on_failed)
        w.finished.connect(lambda: self.busy(False))
        self.worker = w
        w.start()


def main() -> int:
    logging_setup.setup(paths.log_dir())
    app = QApplication(sys.argv)
    win = Main()
    win.resize(560, 560)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
