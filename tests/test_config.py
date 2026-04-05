"""config.json load/save."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reshade_shader_manager.core.config import AppConfig, load_config
from reshade_shader_manager.core.paths import RsmPaths


def test_load_config_ignores_obsolete_create_ini_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older config.json may still list create_ini_if_missing; it must not break load."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    cfg_path = paths.config_json()
    cfg_path.write_text(
        json.dumps(
            {
                "default_variant": "standard",
                "create_ini_if_missing": True,
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(paths)
    assert isinstance(cfg, AppConfig)
    assert cfg.default_variant == "standard"
