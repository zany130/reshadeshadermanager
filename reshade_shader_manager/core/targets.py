"""Game target: paths, PE architecture, graphics API (incl. DX8 via d3d8to9)."""

from __future__ import annotations

import struct
from enum import Enum
from pathlib import Path

# DirectX 8 uses d3d8to9 (``d3d8.dll``) + ReShade as ``d3d9.dll``; see ``reshade.install_reshade``.
DX8_WRAPPER_BASENAME = "d3d8.dll"


class GraphicsAPI(str, Enum):
    OPENGL = "opengl"
    DX8 = "dx8"
    DX9 = "dx9"
    DX10 = "dx10"
    DX11 = "dx11"
    DX12 = "dx12"


class ReShadeVariant(str, Enum):
    STANDARD = "standard"
    ADDON = "addon"


def pe_machine_is_64bit(path: Path) -> bool | None:
    """
    Return True if PE32+, False if PE32, None if not a PE file or unreadable.
    """
    try:
        with path.open("rb") as f:
            mz = f.read(2)
            if mz != b"MZ":
                return None
            f.seek(0x3C)
            (pe_off,) = struct.unpack("<I", f.read(4))
            f.seek(pe_off)
            sig = f.read(4)
            if sig != b"PE\0\0":
                return None
            f.read(20)  # COFF file header
            magic = struct.unpack("<H", f.read(2))[0]
            if magic == 0x20B:
                return True
            if magic == 0x10B:
                return False
            return None
    except OSError:
        return None


def detect_game_arch(game_dir: Path, game_exe: Path | None) -> str:
    """
    Return ``\"32\"`` or ``\"64\"`` for ReShade DLL selection.

    Prefer ``game_exe`` if provided; otherwise probe the first ``*.exe`` in ``game_dir``
    (non-recursive). Raises ``ValueError`` if architecture cannot be determined.
    """
    candidates: list[Path] = []
    if game_exe is not None and game_exe.is_file():
        candidates.append(game_exe)
    else:
        candidates.extend(sorted(game_dir.glob("*.exe")))
    for c in candidates:
        kind = pe_machine_is_64bit(c)
        if kind is True:
            return "64"
        if kind is False:
            return "32"
    raise ValueError("Could not detect game executable architecture (no PE32/PE32+ exe found)")


def proxy_dll_for_api(api: GraphicsAPI) -> str:
    """Destination basename for the ReShade proxy DLL (after any API-specific wrapper)."""
    if api is GraphicsAPI.OPENGL:
        return "opengl32.dll"
    if api is GraphicsAPI.DX8:
        # d3d8to9 supplies ``d3d8.dll``; ReShade loads as D3D9.
        return "d3d9.dll"
    if api is GraphicsAPI.DX9:
        return "d3d9.dll"
    if api in (GraphicsAPI.DX10, GraphicsAPI.DX11, GraphicsAPI.DX12):
        return "dxgi.dll"
    raise ValueError(f"unsupported graphics API: {api}")
