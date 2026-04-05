"""Game manifest roundtrip."""

import json
import logging
from pathlib import Path

import pytest

from reshade_shader_manager.core.manifest import (
    SCHEMA_VERSION,
    GameManifest,
    load_game_manifest,
    new_game_manifest,
    save_game_manifest,
)
from reshade_shader_manager.core.paths import RsmPaths, canonical_game_dir_str, game_id_from_game_dir, new_manifest_path_for_game


def test_manifest_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game_dir = (tmp_path / "g").resolve()
    game_dir.mkdir()
    m = GameManifest(
        game_dir=str(game_dir),
        game_exe=None,
        graphics_api="dx11",
        reshade_version="6.0.0",
        reshade_variant="standard",
        reshade_arch="64",
        enabled_repo_ids=["quint"],
        installed_reshade_files=["dxgi.dll"],
        symlinks_by_repo_id={"quint": ["/tmp/a", "/tmp/b"]},
        enabled_plugin_addon_ids=["swapchain-override"],
        plugin_addon_root_copies={"swapchain-override": ["swapchain_override.addon64"]},
        plugin_addon_companion_symlinks={"swapchain-override": ["/game/reshade-shaders/Shaders/a.fx"]},
    )
    save_game_manifest(paths, m)
    preferred = new_manifest_path_for_game(paths, game_dir, None)
    assert preferred.is_file()
    assert not paths.game_manifest_path(game_id_from_game_dir(game_dir)).is_file()
    m2 = load_game_manifest(paths, game_dir)
    assert m2 is not None
    assert m2.schema_version == SCHEMA_VERSION
    assert m2.enabled_repo_ids == ["quint"]
    assert m2.symlinks_by_repo_id["quint"] == ["/tmp/a", "/tmp/b"]
    assert m2.enabled_plugin_addon_ids == ["swapchain-override"]
    assert m2.plugin_addon_root_copies["swapchain-override"] == ["swapchain_override.addon64"]
    assert m2.plugin_addon_companion_symlinks["swapchain-override"] == [
        "/game/reshade-shaders/Shaders/a.fx"
    ]


def test_load_game_manifest_accepts_symlink_alias_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    real = (tmp_path / "realgame").resolve()
    real.mkdir()
    alias = tmp_path / "aliasgame"
    alias.symlink_to(real, target_is_directory=True)
    save_game_manifest(paths, new_game_manifest(real))
    via_alias = load_game_manifest(paths, alias)
    assert via_alias is not None
    assert via_alias.game_dir == canonical_game_dir_str(real)
    via_real = load_game_manifest(paths, real)
    assert via_real is not None
    assert via_real.game_dir == via_alias.game_dir


def test_manifest_load_schema_v1_migrates_to_v2(tmp_path: Path, monkeypatch) -> None:
    """On-disk schema_version 1 without plugin add-on keys loads as current schema with empty add-on state."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game_dir = (tmp_path / "legacy").resolve()
    game_dir.mkdir()
    gid = game_id_from_game_dir(game_dir)
    mp = paths.game_manifest_path(gid)
    new_path = new_manifest_path_for_game(paths, game_dir, None)
    mp.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "schema_version": 1,
        "game_dir": str(game_dir),
        "game_exe": None,
        "graphics_api": "dx11",
        "reshade_version": "",
        "reshade_variant": "standard",
        "reshade_arch": "64",
        "enabled_repo_ids": [],
        "installed_reshade_files": [],
        "symlinks_by_repo_id": {},
    }
    mp.write_text(json.dumps(legacy, indent=2), encoding="utf-8")

    m = load_game_manifest(paths, game_dir)
    assert m is not None
    assert m.schema_version == SCHEMA_VERSION
    assert m.enabled_plugin_addon_ids == []
    assert m.plugin_addon_root_copies == {}
    assert m.plugin_addon_companion_symlinks == {}
    assert not mp.is_file()
    assert new_path.is_file()

    save_game_manifest(paths, m)
    data = json.loads(new_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["enabled_plugin_addon_ids"] == []
    assert data["plugin_addon_root_copies"] == {}
    assert data["plugin_addon_companion_symlinks"] == {}


def _minimal_manifest_dict(game_dir: str, **extra: object) -> dict:
    d: dict = {
        "schema_version": SCHEMA_VERSION,
        "game_dir": game_dir,
        "game_exe": None,
        "graphics_api": "dx11",
        "reshade_version": "",
        "reshade_variant": "standard",
        "reshade_arch": "64",
        "enabled_repo_ids": [],
        "installed_reshade_files": [],
        "symlinks_by_repo_id": {},
        "enabled_plugin_addon_ids": [],
        "plugin_addon_root_copies": {},
        "plugin_addon_companion_symlinks": {},
    }
    d.update(extra)
    return d


def test_migrate_stale_manifest_filename_preserves_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Pre-v1.0-style file at a non-canonical name moves to {slug}-{fp8}.json."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game = (tmp_path / "wine" / "game").resolve()
    game.mkdir(parents=True)
    target = new_manifest_path_for_game(paths, game, None)
    stale = paths.games_dir() / "stale-pre-canonical.json"
    raw_dir = str(game)
    stale.write_text(
        json.dumps(
            _minimal_manifest_dict(raw_dir, enabled_repo_ids=["keep-me"], reshade_version="5.0.0")
        ),
        encoding="utf-8",
    )
    assert not target.is_file()

    with caplog.at_level(logging.INFO):
        m = load_game_manifest(paths, game)
    assert m is not None
    assert m.enabled_repo_ids == ["keep-me"]
    assert m.reshade_version == "5.0.0"
    assert m.game_dir == canonical_game_dir_str(game)
    assert target.is_file()
    assert not stale.is_file()
    assert "Migrated config to canonical path:" in caplog.text


def test_duplicate_manifests_warn_and_prefer_canonical_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game = (tmp_path / "g2").resolve()
    game.mkdir()
    cgd = canonical_game_dir_str(game)
    target = new_manifest_path_for_game(paths, cgd, None)
    fp8 = target.name.rsplit("-", 1)[-1].removesuffix(".json")
    other = paths.games_dir() / f"other-{fp8}.json"
    target.write_text(
        json.dumps(_minimal_manifest_dict(cgd, enabled_repo_ids=["canonical"])),
        encoding="utf-8",
    )
    other.write_text(
        json.dumps(_minimal_manifest_dict(cgd, enabled_repo_ids=["stale"])),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        m = load_game_manifest(paths, game)
    assert m is not None
    assert m.enabled_repo_ids == ["canonical"]
    assert target.is_file()
    assert other.is_file()
    assert "Duplicate manifests detected for the same game after canonicalization" in caplog.text


def test_manifest_conflict_when_canonical_path_occupied_by_other_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Canonical filename exists but holds a different game_dir; do not overwrite."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game_a = (tmp_path / "a").resolve()
    game_b = (tmp_path / "b").resolve()
    game_a.mkdir()
    game_b.mkdir()
    target_for_a = new_manifest_path_for_game(paths, canonical_game_dir_str(game_a), None)
    target_for_a.write_text(
        json.dumps(_minimal_manifest_dict(str(game_b))),
        encoding="utf-8",
    )
    stale = paths.games_dir() / "only-a.json"
    stale.write_text(json.dumps(_minimal_manifest_dict(str(game_a))), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        m = load_game_manifest(paths, game_a)
    assert m is not None
    assert canonical_game_dir_str(m.game_dir) == canonical_game_dir_str(game_a)
    assert stale.is_file()
    assert target_for_a.is_file()
    assert "Duplicate manifests detected" in caplog.text
