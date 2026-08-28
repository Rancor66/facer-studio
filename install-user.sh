#!/usr/bin/env bash
set -eu

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${HOME}/.local/bin"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

mkdir -p \
    "$DATA_HOME/applications" \
    "$DATA_HOME/icons/hicolor/scalable/apps" \
    "$BIN_HOME" \
    "$CONFIG_HOME/autostart"
ln -sfn "$APP_DIR/facer-studio" "$BIN_HOME/facer-studio"
ln -sfn "$APP_DIR/resources/facer-studio.svg" "$DATA_HOME/icons/hicolor/scalable/apps/facer-studio.svg"
sed -e "s|@EXEC@|$APP_DIR/facer-studio|g" -e "s|@ICON@|$APP_DIR/resources/facer-studio.svg|g" \
    "$APP_DIR/facer-studio.desktop.in" > "$DATA_HOME/applications/facer-studio.desktop"
chmod 755 "$DATA_HOME/applications/facer-studio.desktop"

sed -e "s|@EXEC@|$BIN_HOME/facer-studio|g" -e "s|@ICON@|$APP_DIR/resources/facer-studio.svg|g" \
    "$APP_DIR/facer-studio-autostart.desktop.in" > "$CONFIG_HOME/autostart/facer-studio.desktop"
chmod 644 "$CONFIG_HOME/autostart/facer-studio.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi

echo "Facer Studio установлен в меню приложений и добавлен в автозапуск (в трей)."
