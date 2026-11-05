#!/usr/bin/env sh
# Linux: tarball by default; AppImage if appimagetool is on PATH.
set -eu
tar -C dist -czf dist/lumen-linux-x86_64.tar.gz Lumen
if command -v appimagetool >/dev/null 2>&1; then
  rm -rf dist/Lumen.AppDir && mkdir -p dist/Lumen.AppDir/usr/bin
  cp -r dist/Lumen/* dist/Lumen.AppDir/usr/bin/
  printf '#!/bin/sh\nexec "$APPDIR/usr/bin/Lumen" "$@"\n' > dist/Lumen.AppDir/AppRun && chmod +x dist/Lumen.AppDir/AppRun
  printf '[Desktop Entry]\nName=Lumen\nExec=Lumen\nIcon=lumen\nType=Application\nCategories=Game;\n' > dist/Lumen.AppDir/lumen.desktop
  appimagetool dist/Lumen.AppDir dist/Lumen-x86_64.AppImage
fi
