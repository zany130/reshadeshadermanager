"""Recent games list (mtime walk, valid entries, dedupe)."""

import json
import os
import time
from pathlib import Path

import pytest

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.recent_games import RECENT_GAMES_LIMIT, list_recent_games


def _touch(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RsmPaths:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    p = RsmPaths.from_env()
    p.ensure_layout()
    return p


def _write_manifest(path: Path, game_dir: str, *, game_exe: str | None = None) -> None:
    d: dict = {
        "schema_version": 2,
        "game_dir": game_dir,
        "graphics_api": "dx11",
        "reshade_variant": "standard",
        "reshade_arch": "64",
        "enabled_repo_ids": [],
        "installed_reshade_files": [],
        "symlinks_by_repo_id": {},
        "enabled_plugin_addon_ids": [],
        "plugin_addon_root_copies": {},
        "plugin_addon_companion_symlinks": {},
    }
    if game_exe is not None:
        d["game_exe"] = game_exe
    path.write_text(json.dumps(d), encoding="utf-8")


def test_list_recent_sorts_by_mtime_newest_first(paths: RsmPaths, tmp_path: Path) -> None:
    g1 = (tmp_path / "a").resolve()
    g2 = (tmp_path / "b").resolve()
    g1.mkdir()
    g2.mkdir()
    games = paths.games_dir()
    f1 = games / "a-aaaaaaaa.json"
    f2 = games / "b-bbbbbbbb.json"
    _write_manifest(f1, str(g1))
    _write_manifest(f2, str(g2))
    base = time.time()
    _touch(f1, base - 100)
    _touch(f2, base)

    entries = list_recent_games(paths, limit=5)
    assert len(entries) == 2
    assert entries[0].game_dir.resolve() == g2
    assert entries[0].display_name == "b"
    assert entries[1].game_dir.resolve() == g1


def test_list_recent_prefers_exe_stem_for_display(paths: RsmPaths, tmp_path: Path) -> None:
    g = (tmp_path / "mygame").resolve()
    g.mkdir()
    games = paths.games_dir()
    f = games / "x-11111111.json"
    _write_manifest(f, str(g), game_exe="/wine/prefix/Game.exe")
    _touch(f, time.time())

    entries = list_recent_games(paths, limit=5)
    assert len(entries) == 1
    assert entries[0].display_name == "Game"


def test_list_recent_skips_invalid_json_continues(paths: RsmPaths, tmp_path: Path) -> None:
    g = (tmp_path / "ok").resolve()
    g.mkdir()
    games = paths.games_dir()
    bad = games / "bad.json"
    good = games / "good-00000000.json"
    bad.write_text("{ not json", encoding="utf-8")
    _write_manifest(good, str(g))
    now = time.time()
    _touch(bad, now + 10)
    _touch(good, now)

    entries = list_recent_games(paths, limit=5)
    assert len(entries) == 1
    assert entries[0].game_dir.resolve() == g


def test_list_recent_dedupes_canonical_game_dir(paths: RsmPaths, tmp_path: Path) -> None:
    g = (tmp_path / "same").resolve()
    g.mkdir()
    games = paths.games_dir()
    f1 = games / "one-11111111.json"
    f2 = games / "two-22222222.json"
    _write_manifest(f1, str(g))
    _write_manifest(f2, str(g))
    _touch(f1, time.time() + 5)
    _touch(f2, time.time())

    entries = list_recent_games(paths, limit=5)
    assert len(entries) == 1
    assert entries[0].game_dir.resolve() == g


def test_list_recent_respects_limit(paths: RsmPaths, tmp_path: Path) -> None:
    games = paths.games_dir()
    base = time.time()
    for i in range(10):
        g = (tmp_path / f"g{i}").resolve()
        g.mkdir()
        f = games / f"g{i}-{i:08d}.json"
        _write_manifest(f, str(g))
        _touch(f, base + i)

    entries = list_recent_games(paths, limit=RECENT_GAMES_LIMIT)
    assert len(entries) == RECENT_GAMES_LIMIT
    # Newest files are g9..g4 by mtime
    assert entries[0].display_name == "g9"


def test_list_recent_skips_missing_game_dir_key(paths: RsmPaths, tmp_path: Path) -> None:
    games = paths.games_dir()
    f = games / "x.json"
    f.write_text(
        json.dumps({"schema_version": 2, "graphics_api": "dx11"}),
        encoding="utf-8",
    )
    _touch(f, time.time())
    assert list_recent_games(paths) == []
