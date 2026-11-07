import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect

from lumen.ui.app import Main
from lumen import logging_setup, paths


STYLE = """
QMainWindow, QWidget { background: #0b0d10; color: #f4f0e6; }
QLabel { color: #f4f0e6; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: #14181d; color: #f4f0e6; border: 1px solid #3a414b;
    border-radius: 6px; padding: 6px;
}
QPushButton {
    background: #f2b90b; color: #111318; border: 0; border-radius: 6px;
    padding: 8px 14px; font-weight: 700;
}
QPushButton:hover { background: #ffd34d; }
QPushButton:pressed { background: #c99400; }
QCheckBox::indicator:checked { background: #f2b90b; border: 1px solid #f2b90b; }
QTabWidget::pane { border: 1px solid #303741; }
QTabBar::tab { background: #14181d; color: #aeb6c2; padding: 9px 15px; }
QTabBar::tab:selected { color: #111318; background: #f2b90b; }
"""


def main() -> int:
    logging_setup.setup(paths.log_dir())
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    window = Main()
    window.resize(720, 620)
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
