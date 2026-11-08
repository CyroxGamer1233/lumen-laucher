import os
import sys

if sys.platform != "win32" and not (
    os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lumen.modern_offline import main


if __name__ == "__main__":
    raise SystemExit(main())
