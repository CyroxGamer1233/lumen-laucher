"""Launch the game as a child process (argument list, never a shell string)."""
from __future__ import annotations
import logging, subprocess, threading
from pathlib import Path
from ..logging_setup import redact

log = logging.getLogger("lumen.game")


def launch(cmd: list[str], cwd: Path, game_log: Path) -> subprocess.Popen:
    log.info("Launching: %s", redact(" ".join(cmd[:1] + ["…"] + cmd[-6:])))
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", shell=False)

    def pump() -> None:
        with open(game_log, "a", encoding="utf-8") as f:
            for line in proc.stdout:                       # type: ignore[union-attr]
                f.write(redact(line))
        code = proc.wait()
        log.info("Game exited with code %s", code)

    threading.Thread(target=pump, daemon=True, name="game-log").start()
    return proc
