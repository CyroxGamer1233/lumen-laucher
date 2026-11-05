#!/usr/bin/env sh
# Linux/macOS: build mod, run tests, build launcher bundle.
set -eu
cd "$(dirname "$0")/.."
python -m pip install -e ".[gui,dev]"
python -m pytest -q
(cd client-mod && ./gradlew --no-daemon build)   # needs the Gradle wrapper: run `gradle wrapper` once
python build/build_launcher.py
echo "Bundle in dist/Lumen"
