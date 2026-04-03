"""Shared fixtures for backend tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from reshade_shader_manager.core.paths import RsmPaths


@pytest.fixture
def rsm_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RsmPaths:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    p = RsmPaths.from_env()
    p.ensure_layout()
    return p
