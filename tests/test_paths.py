"""Tests for stable game IDs and path helpers."""

from pathlib import Path

from reshade_shader_manager.core.paths import (
    RsmPaths,
    candidate_game_manifest_paths,
    game_dir_fingerprint8,
    game_id_from_game_dir,
    manifest_slug_candidates,
    new_manifest_path_for_game,
)


def test_game_id_stable(tmp_path: Path) -> None:
    d = tmp_path / "game"
    d.mkdir()
    resolved = d.resolve()
    a = game_id_from_game_dir(resolved)
    b = game_id_from_game_dir(str(resolved))
    assert a == b
    assert len(a) == 64


def test_game_dir_fingerprint8_matches_full_hash_prefix(tmp_path: Path) -> None:
    d = tmp_path / "game"
    d.mkdir()
    resolved = d.resolve()
    gid = game_id_from_game_dir(resolved)
    assert game_dir_fingerprint8(resolved) == gid[:8]


def test_manifest_slug_candidates_prefers_exe_stem(tmp_path: Path) -> None:
    g = (tmp_path / "My Game Dir").resolve()
    g.mkdir(parents=True)
    c = manifest_slug_candidates("/path/to/SomeGame.exe", g)
    assert c[0] == "somegame"
    assert "my-game-dir" in c


def test_new_manifest_path_uses_slug_fp8_pattern(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game_dir = (tmp_path / "g").resolve()
    game_dir.mkdir()
    fp8 = game_dir_fingerprint8(game_dir)
    p = new_manifest_path_for_game(paths, game_dir, None)
    assert p.parent == paths.games_dir()
    assert p.name == f"g-{fp8}.json"


def test_candidate_paths_include_preferred_then_glob_then_legacy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game_dir = (tmp_path / "g").resolve()
    game_dir.mkdir()
    fp8 = game_dir_fingerprint8(game_dir)
    cands = candidate_game_manifest_paths(paths, game_dir, None)
    assert cands[0].name == f"g-{fp8}.json"
    assert cands[-1] == paths.game_manifest_path(game_id_from_game_dir(game_dir))


def test_rsm_paths_no_create(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    p = RsmPaths.from_env()
    assert p.config_dir == tmp_path / "cfg" / "reshade-shader-manager"
    assert p.reshade_latest_cache_path() == p.cache_dir / "reshade_latest_cache.json"
    assert p.ui_state_json() == p.config_dir / "ui_state.json"
