#!/usr/bin/env sh
# macOS: sign, notarize, package. Requires an Apple Developer ID.
set -eu
APP="dist/Lumen.app"
codesign --deep --force --options runtime --timestamp -s "$DEVELOPER_ID" "$APP"
hdiutil create -volname "Lumen" -srcfolder "$APP" -ov -format UDZO dist/Lumen.dmg
xcrun notarytool submit dist/Lumen.dmg --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple dist/Lumen.dmg
