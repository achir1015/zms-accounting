#!/bin/bash
# 建置 macOS 版：dist-mac/資料助秘之一般公司會計.app 與 dist-mac/ZMSAccounting-<版本>-mac.dmg
# 用法（在 Mac 上）：bash tools/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
PY=.venv/bin/python
VER=$($PY -c "import acct; print(acct.APP_VERSION)")
NAME="資料助秘之一般公司會計"
BUNDLE_ID="com.achir.zmsaccounting"
echo "== 版本 $VER"

bash tools/prepare_mariadb_mac.sh

rm -rf build-mac dist-mac build
mkdir -p build-mac dist-mac

# 圖示 PNG → icns
SET=build-mac/icon.iconset; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) assets/icon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o build-mac/icon.icns

echo "== flet pack"
.venv/bin/flet pack main.py -y -n ZMSAccounting -i build-mac/icon.icns --distpath dist-mac \
  --add-data assets:assets --add-data acct/schema.sql:acct \
  --hidden-import edge_tts --hidden-import pymysql --hidden-import qrcode --hidden-import qrcode.image.pil \
  --product-name "$NAME" --product-version "$VER" --bundle-id "$BUNDLE_ID" --copyright "© 2026 吳玉柱"

APP=dist-mac/ZMSAccounting.app
[ -d "$APP" ] || { echo "找不到 $APP"; ls dist-mac; exit 1; }

echo "== 內附 MariaDB"
cp -R packaging/mariadb-mac "$APP/Contents/Resources/mariadb"

PL="$APP/Contents/Info.plist"
pb() { /usr/libexec/PlistBuddy -c "$1" "$PL" 2>/dev/null || true; }
pb "Delete :CFBundleDisplayName"; pb "Add :CFBundleDisplayName string $NAME"
pb "Set :CFBundleName $NAME"
pb "Set :CFBundleShortVersionString $VER"; pb "Set :CFBundleVersion $VER"
pb "Delete :LSMinimumSystemVersion"; pb "Add :LSMinimumSystemVersion string 11.0"
pb "Delete :LSApplicationCategoryType"; pb "Add :LSApplicationCategoryType string public.app-category.finance"
pb "Delete :NSHumanReadableCopyright"; pb "Add :NSHumanReadableCopyright string 系統開發：吳玉柱 先生 與 Claude AI Opus 5.5"
pb "Delete :NSLocalNetworkUsageDescription"
pb "Add :NSLocalNetworkUsageDescription string 連到公司區域網路上的 MariaDB 會計資料庫"
pb "Delete :NSAppleEventsUsageDescription"
pb "Add :NSAppleEventsUsageDescription string 在桌面建立本系統的替身"

FINAL="dist-mac/$NAME.app"
rm -rf "$FINAL"; mv "$APP" "$FINAL"
echo "== 簽章（ad-hoc）"
codesign --force --deep -s - "$FINAL"
codesign --verify --deep --strict "$FINAL" && echo "簽章 OK"

echo "== DMG"
STAGE=build-mac/dmg; rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$FINAL" "$STAGE/$NAME.app"
ln -s /Applications "$STAGE/應用程式"
SIZE_MB=$(( $(du -sm "$STAGE" | cut -f1) + 60 ))
DMG="dist-mac/ZMSAccounting-$VER-mac.dmg"
rm -f "$DMG"
for i in 1 2 3; do
  hdiutil create -volname "$NAME $VER" -srcfolder "$STAGE" -ov -format UDZO -size ${SIZE_MB}m "$DMG" && break
  echo "hdiutil 重試 $i"; sleep 5
done
shasum -a 256 "$DMG"
du -h "$DMG"
echo "BUILD_DONE"
