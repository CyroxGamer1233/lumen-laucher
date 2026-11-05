"""Build a one-folder GUI bundle with PyInstaller (one-folder starts faster and triggers fewer AV false positives than one-file).

    python build/build_launcher.py
Outputs dist/Lumen/ . Sign the result afterwards (see docs/SECURITY.md).
"""
import sys
from pathlib import Path
import PyInstaller.__main__ as pyi

root = Path(__file__).resolve().parent.parent
sep = ";" if sys.platform == "win32" else ":"

args = [
    str(root / "src" / "lumen" / "ui" / "app.py"),
    "--name", "Lumen",
    "--windowed", "--noconfirm", "--clean",
    "--paths", str(root / "src"),
    "--workpath", str(root / "build" / "_work"),
    "--distpath", str(root / "dist"),
    # keyring picks its backend through entry points; PyInstaller can't see those
    "--collect-submodules", "keyring.backends",
    "--hidden-import", "keyring.backends.Windows",
    "--hidden-import", "keyring.backends.macOS",
    "--hidden-import", "keyring.backends.SecretService",
    "--collect-data", "minecraft_launcher_lib",
    "--collect-all", "certifi",
]
# Bundle the sample client mod if it was built (./gradlew build)
mod_jar = next((root / "client-mod" / "build" / "libs").glob("lumen-client-*[0-9].jar"), None) if (root / "client-mod" / "build" / "libs").exists() else None
if mod_jar:
    args += ["--add-data", f"{mod_jar}{sep}bundled_mods"]

pyi.run(args)
