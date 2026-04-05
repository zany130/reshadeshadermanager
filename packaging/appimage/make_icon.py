#!/usr/bin/env python3
"""Validate pre-rendered hicolor icons (no ImageMagick required at build time).

See packaging/README.md for how to regenerate icons when the source logo changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ICON_NAME = "reshade-shader-manager.png"
_SIZES = (64, 128, 256, 512)


def validate_icons() -> None:
    root = Path(__file__).resolve().parent
    for size in _SIZES:
        p = root / "icons" / "hicolor" / f"{size}x{size}" / "apps" / _ICON_NAME
        if not p.is_file():
            raise FileNotFoundError(f"missing pre-rendered icon: {p}")
    top = root / _ICON_NAME
    if not top.is_file():
        raise FileNotFoundError(f"missing AppImage root icon copy: {top}")


def main() -> None:
    try:
        validate_icons()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
