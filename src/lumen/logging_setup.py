"""Rotating file log with automatic secret redaction."""
from __future__ import annotations
import logging, re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    (re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]*"), "<jwt>"),
    (re.compile(r"(--accessToken\s+)\S+"), r"\1<redacted>"),
    (re.compile(r"(Bearer\s+)\S+", re.I), r"\1<redacted>"),
    (re.compile(r"""((?:access|refresh|id)_?token["']?\s*[:=]\s*["']?)[^"'\s,}]+""", re.I), r"\1<redacted>"),
]


def redact(text: str) -> str:
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    try:
        home = str(Path.home())
        if len(home) > 3:
            text = text.replace(home, "~")
    except RuntimeError:
        pass
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    log = logging.getLogger("lumen")
    if log.handlers:
        return log
    log.setLevel(level)
    h = RotatingFileHandler(log_dir / "lumen.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    h.addFilter(RedactingFilter())
    log.addHandler(h)
    return log
