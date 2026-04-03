# PyInstaller spec for reshade-shader-manager (Linux).
# GTK 4 + GObject are expected on the host; PyInstaller still bundles gi bindings
# and typelibs it discovers so the frozen binary can load Gtk from system libs.
# Build on a Fedora-like system with python3-gobject and gtk4 installed.

import sys
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH).resolve().parents[1]
# Prefer this repo over an older `reshade_shader_manager` on sys.path (e.g. pip --user).
sys.path.insert(0, str(ROOT))
MAIN = ROOT / "reshade_shader_manager" / "main.py"

# Collect our package
from PyInstaller.utils.hooks import collect_submodules  # noqa: E402

hidden = collect_submodules("reshade_shader_manager")
hidden += [
    "gi",
    "gi.repository",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.Gio",
    "gi.repository.GLib",
    "gi.repository.Pango",
    "gi.repository.PangoCairo",
    "gi.repository.cairo",
]

a = Analysis(
    [str(MAIN)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="reshade-shader-manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="reshade-shader-manager",
)
