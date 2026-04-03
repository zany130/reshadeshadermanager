"""Persisted main-window geometry (JSON only; no GTK imports)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_MIN_DIM = 320
_MAX_DIM = 10000


@dataclass(frozen=True)
class WindowUiState:
    width: int
    height: int
    maximized: bool = False


def _clamp_dim(n: int) -> int:
    return max(_MIN_DIM, min(_MAX_DIM, n))


def load_window_ui_state(path: Path) -> WindowUiState | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data: Any = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    w = data.get("main_window_width")
    h = data.get("main_window_height")
    m = data.get("main_window_maximized", False)
    if not isinstance(w, int) or not isinstance(h, int):
        return None
    if w < _MIN_DIM or h < _MIN_DIM:
        return None
    return WindowUiState(
        width=_clamp_dim(w),
        height=_clamp_dim(h),
        maximized=bool(m),
    )


def save_window_ui_state(path: Path, state: WindowUiState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "main_window_width": _clamp_dim(state.width),
        "main_window_height": _clamp_dim(state.height),
        "main_window_maximized": state.maximized,
    }
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)
