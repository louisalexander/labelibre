#!/bin/bash
# Installs "Label Printer.app" (Supvan T50M Pro batch printer for .aml labels)
# and a `labelprint` command-line tool.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${LABELPRINTER_DEST:-/Applications}"
[ -w "$DEST" ] || DEST="$HOME/Applications"
mkdir -p "$DEST"
APP="$DEST/Label Printer.app"
RES="$APP/Contents/Resources"

command -v uv >/dev/null || { echo "uv is required: brew install uv"; exit 1; }

echo "Installing to $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES"
cp -R "$SRC/supvan" "$RES/supvan"
find "$RES/supvan" -name __pycache__ -prune -exec rm -rf {} +
uv venv -q --python 3.13 "$RES/venv"
uv pip install -q --python "$RES/venv/bin/python" -r "$SRC/requirements.txt"

cat > "$APP/Contents/MacOS/LabelPrinter" <<'SH'
#!/bin/bash
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
cd "$RES"
exec "$RES/venv/bin/python" -m supvan.app "$@" >> "$HOME/Library/Logs/LabelPrinter.log" 2>&1
SH
chmod +x "$APP/Contents/MacOS/LabelPrinter"

cat > "$APP/Contents/Info.plist" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Label Printer</string>
  <key>CFBundleDisplayName</key><string>Label Printer</string>
  <key>CFBundleIdentifier</key><string>local.labelprinter.supvan</string>
  <key>CFBundleExecutable</key><string>LabelPrinter</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSBluetoothAlwaysUsageDescription</key><string>Label Printer connects to your SUPVAN label printer over Bluetooth.</string>
</dict></plist>
PL

# icon
"$RES/venv/bin/python" -I "$SRC/tools/make_icon.py" "$RES/AppIcon.icns" || true
codesign --force --deep -s - "$APP" 2>/dev/null || true

# command-line tool
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/labelprint" <<SH
#!/bin/bash
cd "$RES" && exec "$RES/venv/bin/python" -m supvan.cli "\$@"
SH
chmod +x "$HOME/.local/bin/labelprint"

echo "Done."
echo "  App:  $APP  (open it from Applications / Spotlight: \"Label Printer\")"
echo "  CLI:  ~/.local/bin/labelprint print *.aml   (labelprint --help)"
