"""Tests for persisted window UI state (JSON)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reshade_shader_manager.core.ui_state import (
    WindowUiState,
    load_window_ui_state,
    save_window_ui_state,
)


def test_load_missing_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "ui_state.json"
    assert load_window_ui_state(p) is None


def test_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "ui_state.json"
    save_window_ui_state(p, WindowUiState(width=800, height=600, maximized=True))
    got = load_window_ui_state(p)
    assert got is not None
    assert got.width == 800
    assert got.height == 600
    assert got.maximized is True


def test_clamps_oversized_dimensions(tmp_path: Path) -> None:
    p = tmp_path / "ui_state.json"
    save_window_ui_state(p, WindowUiState(width=50000, height=400, maximized=False))
    got = load_window_ui_state(p)
    assert got is not None
    assert got.width == 10000
    assert got.height == 400


@pytest.mark.parametrize(
    "payload",
    [
        "not an object",
        {"main_window_width": "x", "main_window_height": 600},
        {"main_window_width": 800},
        {"main_window_width": 800, "main_window_height": 100},
    ],
)
def test_load_invalid_returns_none(tmp_path: Path, payload) -> None:
    import json

    p = tmp_path / "ui_state.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert load_window_ui_state(p) is None
