#!/usr/bin/env bash
set -euo pipefail

APP_NAME="com.zdplayer"
APP_ID="com.zdplayer"
BIN_NAME="zdplayer"
VERSION="1.0"
ARCH="all"
PKG_DIR="${APP_NAME}_${VERSION}_${ARCH}"
STAGE_LIB_DIR="$PKG_DIR/usr/lib/zdplayer"

cd "$(dirname "$0")"

assert_not_packaged() {
    local path="$1"
    if find "$PKG_DIR" -type f | grep -Fq -- "$path"; then
        echo "Refusing to build: forbidden file packaged -> $path" >&2
        exit 1
    fi
}

# Clean previous build
rm -rf "$PKG_DIR" "${PKG_DIR}.deb"

# Create directory structure
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$STAGE_LIB_DIR"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/64x64/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/48x48/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/32x32/apps"
mkdir -p "$PKG_DIR/usr/share/metainfo"
mkdir -p "$PKG_DIR/usr/share/pixmaps"

# Copy application source without caches or user data.
while IFS= read -r -d '' source_file; do
    rel_path="${source_file#src/}"
    install -Dm644 "$source_file" "$STAGE_LIB_DIR/$rel_path"
done < <(
    find src -type f \
        \( -name '*.py' -o -name 'logo.png' \) \
        ! -path '*/__pycache__/*' \
        -print0
)

# Create launcher script
cat > "$PKG_DIR/usr/bin/${BIN_NAME}" << 'LAUNCHER'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/usr/lib/zdplayer")
from zdplayer.app import main
sys.exit(main())
LAUNCHER
chmod 755 "$PKG_DIR/usr/bin/${BIN_NAME}"

# Desktop file
cp com.zdplayer.desktop "$PKG_DIR/usr/share/applications/"

# AppData
cp com.zdplayer.appdata.xml "$PKG_DIR/usr/share/metainfo/"

# Icons (resize logo for various sizes)
for size in 32 48 64 128; do
    if command -v convert &>/dev/null; then
        convert src/zdplayer/logo.png -resize ${size}x${size} \
            "$PKG_DIR/usr/share/icons/hicolor/${size}x${size}/apps/${APP_ID}.png"
    elif python3 - <<'PY' >/dev/null 2>&1
from PIL import Image  # noqa: F401
PY
    then
        python3 - "$size" "src/zdplayer/logo.png" \
            "$PKG_DIR/usr/share/icons/hicolor/${size}x${size}/apps/${APP_ID}.png" <<'PY'
import sys
from PIL import Image

size = int(sys.argv[1])
src = sys.argv[2]
dst = sys.argv[3]

image = Image.open(src).convert("RGBA")
image.thumbnail((size, size), Image.Resampling.LANCZOS)
canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
offset = ((size - image.width) // 2, (size - image.height) // 2)
canvas.paste(image, offset, image)
canvas.save(dst)
PY
    else
        cp src/zdplayer/logo.png \
            "$PKG_DIR/usr/share/icons/hicolor/${size}x${size}/apps/${APP_ID}.png"
    fi
done

cp "$PKG_DIR/usr/share/icons/hicolor/128x128/apps/${APP_ID}.png" \
    "$PKG_DIR/usr/share/pixmaps/${APP_ID}.png"

# Calculate installed size
INSTALLED_SIZE=$(du -sk "$PKG_DIR" | cut -f1)

# DEBIAN/control
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: com.zdplayer
Version: ${VERSION}
Section: video
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), python3-gi, python3-requests, gir1.2-gtk-3.0, gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-plugins-good, gstreamer1.0-gtk3
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Zafer Demir <zfrdmr@protonmail.com>
Homepage: https://github.com/zfrdemir/zd-player
Description: ZD PLAYER - IPTV Player
 ZD PLAYER is an IPTV player for Linux supporting
 Xtream API and M3U playlist formats.
 .
 Features include live TV, movies, series playback,
 multi-language interface, color balance settings,
 audio/subtitle track selection and fullscreen mode.
 .
 This application does not host or provide any content.
EOF

# DEBIAN/postinst
cat > "$PKG_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# DEBIAN/postrm
cat > "$PKG_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
EOF
chmod 755 "$PKG_DIR/DEBIAN/postrm"

# Guardrails: user-specific state must never be bundled.
assert_not_packaged "/state.json"
assert_not_packaged "/settings.json"
assert_not_packaged "/__pycache__/"
assert_not_packaged ".pyc"

# Build the .deb
dpkg-deb --build --root-owner-group "$PKG_DIR"

echo ""
echo "✅ Paket oluşturuldu: ${PKG_DIR}.deb"
echo ""
echo "Kurulum:  sudo dpkg -i ${PKG_DIR}.deb"
echo "Kaldırma: sudo apt remove com.zdplayer"
