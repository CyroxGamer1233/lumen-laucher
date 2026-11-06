"""Lumen v3: black/yellow pixel-inspired launcher shell."""
from __future__ import annotations

import sys
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSlider,
    QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__, catalog, config, paths, servers, skins, session
from .modern import LaunchWorker, SignInWorker


THEME = """
QMainWindow,QWidget{background:#080909;color:#f7f2dc;font-family:'Courier New';}
QTabWidget::pane{border:1px solid #34301d;background:#10110e;}
QTabBar::tab{background:#14150f;color:#8e8b78;padding:12px 16px;border:0;border-bottom:2px solid transparent;}
QTabBar::tab:selected{color:#f5c842;border-bottom:2px solid #f5c842;}
QFrame#card{background:#12130f;border:1px solid #39351d;border-radius:10px;}
QLabel#brand{color:#f5c842;font-size:24px;font-weight:700;}
QLabel#title{color:#f5c842;font-size:26px;font-weight:700;}
QLabel#muted{color:#aaa58e;}
QLineEdit,QComboBox,QListWidget{background:#090a08;color:#f7f2dc;border:1px solid #4b4525;border-radius:5px;padding:8px;}
QPushButton{background:#252314;color:#f7f2dc;border:1px solid #665b2b;border-radius:5px;padding:9px 14px;}
QPushButton:hover{background:#3a3214;border-color:#f5c842;color:#f5c842;}
QPushButton#primary{background:#f5c842;color:#090a08;font-weight:700;border:0;padding:12px 22px;}
QCheckBox{color:#d5cfb6;spacing:8px;}
QSlider::groove:horizontal{height:5px;background:#39351d;}
QSlider::handle:horizontal{width:14px;margin:-5px 0;background:#f5c842;border-radius:7px;}
"""


def lbl(value, name=""):
    w = QLabel(value)
    if name:
        w.setObjectName(name)
    return w


def card():
    w = QFrame()
    w.setObjectName("card")
    return w


class CatalogWorker(QThread):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, query, kind, version, loader):
        super().__init__()
        self.query, self.kind, self.version, self.loader = query, kind, version, loader

    def run(self):
        try:
            self.done.emit(catalog.search(self.query, self.kind, self.version, self.loader))
        except Exception as exc:
            self.failed.emit(str(exc))


class ServerWorker(QThread):
    done = Signal(object)

    def __init__(self, host, port):
        super().__init__()
        self.host, self.port = host, port

    def run(self):
        self.done.emit(servers.query(self.host, self.port))


class SkinWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, value):
        super().__init__()
        self.value = value

    def run(self):
        try:
            self.done.emit(skins.lookup(self.value))
        except Exception as exc:
            self.failed.emit(str(exc))


class LauncherV3(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LUMEN // v{__version__}")
        self.resize(1180, 760)
        self.setMinimumSize(980, 650)
        self.setStyleSheet(THEME)
        self.settings = config.load(paths.config_path())
        self.store = session.store()
        self.worker = None
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self.animate_tab)
        self.tabs.addTab(self.play_tab(), "PLAY")
        self.tabs.addTab(self.server_tab(), "SERVERS")
        self.tabs.addTab(self.catalog_tab("mods"), "MODS")
        self.tabs.addTab(self.catalog_tab("shaders"), "SHADERS")
        self.tabs.addTab(self.catalog_tab("modpacks"), "MODPACKS")
        self.tabs.addTab(self.skin_tab(), "SKINS")
        self.tabs.addTab(self.accounts_tab(), "ACCOUNTS")
        self.tabs.addTab(self.settings_tab(), "SETTINGS")

    def shell(self, title, subtitle):
        page, lay = QWidget(), QVBoxLayout()
        page.setLayout(lay)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.addWidget(lbl("LUMEN // V3", "brand"))
        lay.addWidget(lbl(title, "title"))
        lay.addWidget(lbl(subtitle, "muted"))
        return page, lay

    def play_tab(self):
        page, lay = self.shell("PLAY", "Your instance, your rules.")
        panel, form = card(), QFormLayout()
        panel.setLayout(form)
        self.version = QComboBox()
        self.version.addItems(["1.21.1", "1.20.1", "1.21.4"])
        self.version.setCurrentText(self.settings.mc_version)
        self.loader = QComboBox()
        self.loader.addItems(["fabric", "forge", "vanilla"])
        self.loader.setCurrentText(self.settings.loader)
        self.mode = QComboBox()
        self.mode.addItems(["Microsoft account", "Offline account"])
        self.performance = QCheckBox("Install performance mods")
        self.performance.setChecked(self.settings.mod_profile == "performance")
        self.force = QCheckBox("Launch even if mod checks report errors")
        form.addRow("Minecraft", self.version)
        form.addRow("Loader", self.loader)
        form.addRow("Account", self.mode)
        form.addRow("", self.performance)
        form.addRow("", self.force)
        lay.addWidget(panel)
        play = QPushButton("▶  LAUNCH GAME")
        play.setObjectName("primary")
        play.clicked.connect(self.launch_game)
        lay.addWidget(play, 0, Qt.AlignLeft)
        self.play_status = lbl("Ready.", "muted")
        lay.addWidget(self.play_status)
        lay.addStretch()
        return page

    def server_tab(self):
        page, lay = self.shell("SERVERS", "Ping Java servers and inspect their live status.")
        row = QHBoxLayout()
        self.server_host = QLineEdit()
        self.server_host.setPlaceholderText("play.example.net")
        self.server_port = QLineEdit("25565")
        ping = QPushButton("PING SERVER")
        ping.clicked.connect(self.ping_server)
        row.addWidget(self.server_host, 1)
        row.addWidget(self.server_port)
        row.addWidget(ping)
        lay.addLayout(row)
        self.server_result = lbl("No server checked yet.", "muted")
        lay.addWidget(self.server_result)
        self.server_details = QListWidget()
        lay.addWidget(self.server_details, 1)
        return page

    def catalog_tab(self, kind):
        page, lay = self.shell(kind.upper(), f"Discover {kind} from the public Modrinth API.")
        row = QHBoxLayout()
        query = QLineEdit()
        query.setPlaceholderText(f"Search {kind}...")
        button = QPushButton("SEARCH")
        row.addWidget(query, 1)
        row.addWidget(button)
        lay.addLayout(row)
        results = QListWidget()
        lay.addWidget(results, 1)
        button.clicked.connect(lambda: self.search_catalog(kind, query.text(), results))
        query.returnPressed.connect(button.click)
        return page

    def skin_tab(self):
        page, lay = self.shell("SKINS", "Look up a player skin from Mojang's profile service.")
        row = QHBoxLayout()
        value = QLineEdit()
        value.setPlaceholderText("Player name or UUID")
        button = QPushButton("LOOK UP")
        row.addWidget(value, 1)
        row.addWidget(button)
        lay.addLayout(row)
        self.skin_result = lbl("Enter a UUID to inspect its skin textures.", "muted")
        lay.addWidget(self.skin_result)
        self.skin_url = QLineEdit()
        self.skin_url.setReadOnly(True)
        lay.addWidget(self.skin_url)
        button.clicked.connect(lambda: self.lookup_skin(value.text().strip()))
        return page

    def accounts_tab(self):
        page, lay = self.shell("ACCOUNTS", "Secure Microsoft sign-in and owner-gated offline profiles.")
        self.accounts_label = lbl("", "muted")
        lay.addWidget(self.accounts_label)
        sign = QPushButton("SIGN IN WITH MICROSOFT")
        sign.clicked.connect(self.sign_in)
        lay.addWidget(sign, 0, Qt.AlignLeft)
        offline, form = card(), QFormLayout()
        offline.setLayout(form)
        self.offline_name = QLineEdit(self.settings.offline_username)
        self.offline_state = lbl("", "muted")
        form.addRow("Offline username", self.offline_name)
        form.addRow("", self.offline_state)
        save = QPushButton("SAVE OFFLINE PROFILE")
        save.clicked.connect(self.save_settings)
        form.addRow("", save)
        lay.addWidget(offline)
        lay.addStretch()
        self.refresh_accounts()
        return page

    def settings_tab(self):
        page, lay = self.shell("SETTINGS", "Launcher preferences and API options.")
        panel, form = card(), QFormLayout()
        panel.setLayout(form)
        self.client_id = QLineEdit(self.settings.ms_client_id)
        self.profile = QComboBox()
        self.profile.addItems(["low_end", "balanced", "high_end"])
        self.profile.setCurrentText(self.settings.jvm_profile)
        form.addRow("Azure client ID", self.client_id)
        form.addRow("JVM profile", self.profile)
        save = QPushButton("SAVE SETTINGS")
        save.clicked.connect(self.save_settings)
        form.addRow("", save)
        lay.addWidget(panel)
        lay.addStretch()
        return page

    def animate_tab(self, index):
        page = self.tabs.widget(index)
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.25)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    def save_settings(self):
        self.settings.ms_client_id = getattr(self, "client_id", QLineEdit()).text().strip()
        self.settings.mc_version = self.version.currentText().strip()
        self.settings.loader = self.loader.currentText()
        self.settings.jvm_profile = self.profile.currentText()
        self.settings.offline_username = self.offline_name.text().strip() or "Player"
        self.settings.mod_profile = "performance" if self.performance.isChecked() else "minimal"
        config.save(self.settings, paths.config_path())
        self.offline_state.setText("Saved. Offline mode requires one verified Microsoft sign-in.")

    def refresh_accounts(self):
        accounts = self.store.list_accounts()
        names = ", ".join(v["username"] for v in accounts.values()) or "No Microsoft account saved"
        self.accounts_label.setText(f"Saved accounts: {names}")
        self.offline_state.setText("Offline unlocked." if self.store.has_verified_ownership()
                                   else "Offline locked until ownership is verified.")

    def sign_in(self):
        if not session.client_id(self.settings):
            QMessageBox.information(self, "Client ID needed", "Set the Azure client ID in Settings first.")
            self.tabs.setCurrentIndex(7)
            return
        self.worker = SignInWorker(self.settings)
        self.worker.code.connect(lambda code, url: webbrowser.open(url))
        self.worker.done.connect(lambda name: self.refresh_accounts())
        self.worker.failed.connect(lambda msg: QMessageBox.warning(self, "Sign-in failed", msg))
        self.worker.start()

    def launch_game(self):
        self.save_settings()
        offline = self.mode.currentIndex() == 1
        if offline and not self.store.has_verified_ownership():
            QMessageBox.information(self, "Offline locked", "Sign in once to verify ownership first.")
            self.tabs.setCurrentIndex(6)
            return
        if not offline and not self.store.list_accounts():
            QMessageBox.information(self, "Sign in first", "Add a Microsoft account first.")
            self.tabs.setCurrentIndex(6)
            return
        self.play_status.setText("Launching...")
        self.worker = LaunchWorker(self.settings, offline, self.performance.isChecked(), self.force.isChecked())
        self.worker.status.connect(self.play_status.setText)
        self.worker.failed.connect(lambda msg: self.play_status.setText(f"Error: {msg}"))
        self.worker.start()

    def ping_server(self):
        host = self.server_host.text().strip()
        if not host:
            return
        try:
            port = int(self.server_port.text() or "25565")
        except ValueError:
            self.server_result.setText("Invalid port.")
            return
        self.server_result.setText("Pinging...")
        self.worker = ServerWorker(host, port)
        self.worker.done.connect(self.show_server)
        self.worker.start()

    def show_server(self, result):
        self.server_details.clear()
        if not result.online:
            self.server_result.setText(f"● OFFLINE  {result.error or 'No response'}")
            return
        self.server_result.setText(f"● ONLINE  {result.latency_ms} ms")
        for line in (f"Version: {result.version}", f"Players: {result.players_online}/{result.players_max}",
                     f"MOTD: {result.motd}"):
            QListWidgetItem(line, self.server_details)

    def search_catalog(self, kind, query, widget):
        widget.clear()
        widget.addItem("Searching Modrinth...")
        self.worker = CatalogWorker(query, kind, self.version.currentText(), self.loader.currentText())
        self.worker.done.connect(lambda items: self.show_projects(widget, items))
        self.worker.failed.connect(lambda msg: self.show_projects(widget, [], msg))
        self.worker.start()

    def show_projects(self, widget, projects, error=""):
        widget.clear()
        if error:
            widget.addItem(f"Error: {error}")
            return
        for project in projects:
            item = QListWidgetItem(f"{project.title}  ·  {project.downloads:,} downloads  ·  {project.source}")
            item.setToolTip(project.description)
            widget.addItem(item)
        if not projects:
            widget.addItem("No matching projects found.")

    def lookup_skin(self, value):
        if not value:
            return
        self.skin_result.setText("Looking up profile...")
        self.worker = SkinWorker(value)
        self.worker.done.connect(lambda skin: (self.skin_result.setText(f"{skin.name} · {skin.model} model"),
                                               self.skin_url.setText(skin.skin_url or "No skin URL")))
        self.worker.failed.connect(lambda msg: self.skin_result.setText(f"Lookup failed: {msg}"))
        self.worker.start()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Lumen Launcher")
    app.setFont(QFont("Courier New", 10))
    window = LauncherV3()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

