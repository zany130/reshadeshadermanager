#!/usr/bin/env bash
# Simple AppImage build: PyInstaller (onedir) + linuxdeploy/appimagetool-style AppDir.
# Prerequisites (Fedora / similar):
#   - python3, python3-pip, python3-gobject, gtk4
#   - wget or curl (to fetch appimagetool once)
#   - fuse for running AppImage (optional)
#
# Usage: from repo root OR from this directory:
#   ./packaging/appimage/build_appimage.sh

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
cd "${ROOT}"

APPDIR="${SCRIPT_DIR}/AppDir"
DIST="${ROOT}/dist/reshade-shader-manager"
VERSION="${RSM_APPIMAGE_VERSION:-0.6.0}"
APPIMAGETOOL="${APPIMAGETOOL:-${SCRIPT_DIR}/tools/appimagetool}"

echo "==> Repo root: ${ROOT}"
echo "==> Version:   ${VERSION}"

command -v python3 >/dev/null || { echo "python3 required"; exit 1; }

echo "==> Validating pre-rendered icons"
python3 "${SCRIPT_DIR}/make_icon.py"

echo "==> Installing PyInstaller (user/site)"
python3 -m pip install --user -q "pyinstaller>=6.0"
export PATH="${HOME}/.local/bin:${PATH}"

echo "==> PyInstaller (onedir)"
rm -rf "${ROOT}/build" "${ROOT}/dist"
python3 -m PyInstaller --clean --noconfirm "${SCRIPT_DIR}/rsm.spec"

if [[ ! -x "${DIST}/reshade-shader-manager" ]]; then
  echo "Expected executable missing: ${DIST}/reshade-shader-manager"
  exit 1
fi

echo "==> Assemble AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
cp -a "${DIST}/." "${APPDIR}/usr/bin/"

install -m0755 "${SCRIPT_DIR}/AppRun" "${APPDIR}/AppRun"

mkdir -p "${APPDIR}/usr/share/applications"
cp "${SCRIPT_DIR}/reshade-shader-manager.desktop" "${APPDIR}/reshade-shader-manager.desktop"
cp "${SCRIPT_DIR}/reshade-shader-manager.desktop" "${APPDIR}/usr/share/applications/reshade-shader-manager.desktop"

for _size in 64 128 256 512; do
  mkdir -p "${APPDIR}/usr/share/icons/hicolor/${_size}x${_size}/apps"
  cp "${SCRIPT_DIR}/icons/hicolor/${_size}x${_size}/apps/reshade-shader-manager.png" \
    "${APPDIR}/usr/share/icons/hicolor/${_size}x${_size}/apps/reshade-shader-manager.png"
done
cp "${SCRIPT_DIR}/reshade-shader-manager.png" "${APPDIR}/reshade-shader-manager.png"

echo "==> Fetch appimagetool if needed"
mkdir -p "${SCRIPT_DIR}/tools"
if [[ ! -x "${APPIMAGETOOL}" ]]; then
  URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
  echo "Downloading appimagetool -> ${APPIMAGETOOL}"
  if command -v wget >/dev/null; then
    wget -q -O "${APPIMAGETOOL}.download" "${URL}"
  else
    curl -sL -o "${APPIMAGETOOL}.download" "${URL}"
  fi
  mv "${APPIMAGETOOL}.download" "${APPIMAGETOOL}"
  chmod +x "${APPIMAGETOOL}"
fi

OUT="${SCRIPT_DIR}/reshade-shader-manager-${VERSION}-x86_64.AppImage"
echo "==> appimagetool -> ${OUT}"
ARCH=x86_64 VERSION="${VERSION}" "${APPIMAGETOOL}" "${APPDIR}" "${OUT}"

ls -lh "${OUT}"
echo ""
echo "Run:  ${OUT}"
echo "Or:   chmod +x '${OUT}' && '${OUT}'"
