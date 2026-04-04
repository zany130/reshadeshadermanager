"""CLI entry (no GTK imports in tests)."""

import json
from pathlib import Path

import pytest

from reshade_shader_manager.cli import main
from reshade_shader_manager.core.manifest import GameManifest, SCHEMA_VERSION, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths


def test_cli_help_system_exit() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_cli_catalog_refresh_help_system_exit() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["catalog", "refresh", "--help"])
    assert excinfo.value.code == 0


def test_cli_game_inspect_missing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    RsmPaths.from_env().ensure_layout()
    game_dir = (tmp_path / "g").resolve()
    game_dir.mkdir()
    assert main(["game", "inspect", "--game-dir", str(game_dir)]) != 0


def test_cli_game_inspect_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        symlinks_by_repo_id={},
    )
    save_game_manifest(paths, m)
    assert main(["game", "inspect", "--game-dir", str(game_dir), "--json"]) == 0


def test_cli_shaders_apply_requires_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    RsmPaths.from_env().ensure_layout()
    game_dir = (tmp_path / "g").resolve()
    game_dir.mkdir()
    assert main(["shaders", "apply", "--game-dir", str(game_dir)]) != 0
