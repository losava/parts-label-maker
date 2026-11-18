#!/bin/sh
# Install Parts Label for the current user. Does not need administrator rights.
# Your parts list and printer setting are not part of this package.
set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PREFIX="${HOME}/.local"
APP_DIR="${PREFIX}/lib/parts-label"
BIN="${PREFIX}/bin/parts-label"

mkdir -p "${PREFIX}/bin" "${PREFIX}/share/applications" \
    "${PREFIX}/share/icons/hicolor/256x256/apps"
rm -rf "${APP_DIR}"
cp -a "${HERE}/PartsLabel" "${APP_DIR}"
cat > "${BIN}" << EOF
#!/bin/sh
exec "${APP_DIR}/PartsLabel" "\$@"
EOF
chmod 755 "${BIN}" "${APP_DIR}/PartsLabel"

sed "s|^Exec=.*|Exec=${BIN}|" "${HERE}/parts-label.desktop" \
    > "${PREFIX}/share/applications/parts-label.desktop"
cp "${HERE}/parts-label.png" "${PREFIX}/share/icons/hicolor/256x256/apps/parts-label.png"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${PREFIX}/share/applications" >/dev/null 2>&1 || true
fi

echo "Installed Parts Label for this user."
echo "  Menu:  Parts Label"
echo "  Run:   ${BIN}"
echo ""
echo "If the command is not found, log out and back in so ~/.local/bin is on PATH."
echo "Parts lists and the printer setting stay in ~/.local/share/parts-label-maker"
echo "Removing this program does not delete that folder."
