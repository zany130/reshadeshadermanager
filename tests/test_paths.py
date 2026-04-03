"""Tests for stable game IDs and path helpers."""

from pathlib import Path

from reshade_shader_manager.core.paths import RsmPaths, game_id_from_game_dir


def test_game_id_stable(tmp_path: Path) -> None:
    d = tmp_path / "game"
    d.mkdir()
    resolved = d.resolve()
    a = game_id_from_game_dir(resolved)
    b = game_id_from_game_dir(str(resolved))
    assert a == b
    assert len(a) == 64


def test_rsm_paths_no_create(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    p = RsmPaths.from_env()
    assert p.config_dir == tmp_path / "cfg" / "reshade-shader-manager"
    assert p.reshade_latest_cache_path() == p.cache_dir / "reshade_latest_cache.json"
