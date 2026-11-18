#!/usr/bin/env bash
# Build the Linux tarball, .deb, and AppImage from a PyInstaller folder.
# Run from anywhere. Needs the Python deps in requirements.txt plus PyInstaller.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "${ROOT}"

if python -c "import PyInstaller" >/dev/null 2>&1; then
    PYTHON=python
elif python3 -c "import PyInstaller" >/dev/null 2>&1; then
    PYTHON=python3
else
    echo "PyInstaller is not installed. Run: python -m pip install -r requirements-dev.txt" >&2
    exit 1
fi

VERSION=$("${PYTHON}" -c "import version; print(version.__version__)")
ARCH=$(uname -m)
case "${ARCH}" in
    x86_64) DEB_ARCH=amd64 ;;
    aarch64|arm64) DEB_ARCH=arm64 ;;
    *) DEB_ARCH=${ARCH} ;;
esac

echo "Building Parts Label ${VERSION} for ${ARCH}"

"${PYTHON}" -m PyInstaller --noconfirm --clean --windowed --name PartsLabel \
    --collect-all barcode \
    --collect-all reportlab \
    --collect-all PIL \
    parts_label_app.py

PKG="${ROOT}/dist/packages"
STAGE="${ROOT}/dist/stage"
APPDIR="${ROOT}/dist/PartsLabel.AppDir"
DEBROOT="${ROOT}/dist/deb-root"
rm -rf "${PKG}" "${STAGE}" "${APPDIR}" "${DEBROOT}"
mkdir -p "${PKG}"

NAME="PartsLabel-${VERSION}-linux-${ARCH}"
TAR_ROOT="${STAGE}/${NAME}"
mkdir -p "${TAR_ROOT}"
cp -a "${ROOT}/dist/PartsLabel" "${TAR_ROOT}/PartsLabel"
cp "${ROOT}/packaging/linux/parts-label.desktop" "${TAR_ROOT}/parts-label.desktop"
cp "${ROOT}/packaging/linux/install.sh" "${TAR_ROOT}/install.sh"
cp "${ROOT}/packaging/parts-label.png" "${TAR_ROOT}/parts-label.png"
chmod 755 "${TAR_ROOT}/install.sh" "${TAR_ROOT}/PartsLabel/PartsLabel"
cat > "${TAR_ROOT}/README.txt" << EOF
Parts Label ${VERSION}
======================

Install for this user (no administrator):

    ./install.sh

Then open Parts Label from the app menu, or run ~/.local/bin/parts-label.

Printing uses CUPS. Add the Zebra GC420d as a raw queue and pick it in the
app. Generated labels and your parts-list path are stored in
~/.local/share/parts-label-maker (or \$XDG_DATA_HOME), not in this folder.

Uninstall by deleting ~/.local/lib/parts-label, ~/.local/bin/parts-label,
and ~/.local/share/applications/parts-label.desktop.
Do not delete the data folder if you want to keep the parts list path.
EOF
tar -C "${STAGE}" -czf "${PKG}/${NAME}.tar.gz" "${NAME}"

# .deb — program files under /usr, user data stays in the home directory.
mkdir -p "${DEBROOT}/DEBIAN" \
    "${DEBROOT}/usr/lib/parts-label" \
    "${DEBROOT}/usr/bin" \
    "${DEBROOT}/usr/share/applications" \
    "${DEBROOT}/usr/share/icons/hicolor/256x256/apps"
cp -a "${ROOT}/dist/PartsLabel/." "${DEBROOT}/usr/lib/parts-label/"
cat > "${DEBROOT}/usr/bin/parts-label" << 'EOF'
#!/bin/sh
exec /usr/lib/parts-label/PartsLabel "$@"
EOF
chmod 755 "${DEBROOT}/usr/bin/parts-label" "${DEBROOT}/usr/lib/parts-label/PartsLabel"
sed 's|^Exec=.*|Exec=/usr/bin/parts-label|' \
    "${ROOT}/packaging/linux/parts-label.desktop" \
    > "${DEBROOT}/usr/share/applications/parts-label.desktop"
cp "${ROOT}/packaging/parts-label.png" \
    "${DEBROOT}/usr/share/icons/hicolor/256x256/apps/parts-label.png"
cat > "${DEBROOT}/DEBIAN/control" << EOF
Package: parts-label-maker
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${DEB_ARCH}
Maintainer: losava <losava@users.noreply.github.com>
Depends: libc6
Recommends: cups-client
Description: Shop parts label maker
 Print 3x2 inch Code 128 labels for a Zebra GC420d.
 The parts list and printer setting stay in the user data folder
 and are kept across upgrades and removal.
EOF
DEB_NAME="parts-label-maker_${VERSION}_${DEB_ARCH}.deb"
dpkg-deb --root-owner-group --build "${DEBROOT}" "${PKG}/${DEB_NAME}"

# AppImage — skip with --no-appimage when the tool cannot be downloaded.
if [[ "${1:-}" == "--no-appimage" ]]; then
    echo "Skipping AppImage"
else
    mkdir -p "${APPDIR}/usr/bin"
    cp -a "${ROOT}/dist/PartsLabel/." "${APPDIR}/usr/bin/"
    cp "${ROOT}/packaging/parts-label.png" "${APPDIR}/parts-label.png"
    cat > "${APPDIR}/parts-label.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Parts Label
Comment=Print 3x2 inch Code 128 parts labels
Exec=PartsLabel
Icon=parts-label
Terminal=false
Categories=Office;Utility;
EOF
    cat > "${APPDIR}/AppRun" << 'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/usr/bin/PartsLabel" "$@"
EOF
    chmod 755 "${APPDIR}/AppRun" "${APPDIR}/usr/bin/PartsLabel"
    TOOL="${ROOT}/dist/appimagetool"
    if [[ ! -x "${TOOL}" ]]; then
        curl -fsSL -o "${TOOL}" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
        chmod 755 "${TOOL}"
    fi
    APPIMAGE_EXTRACT_AND_RUN=1 ARCH="${ARCH}" "${TOOL}" "${APPDIR}" \
        "${PKG}/PartsLabel-${VERSION}-${ARCH}.AppImage"
fi

echo "Packages:"
ls -lh "${PKG}"
