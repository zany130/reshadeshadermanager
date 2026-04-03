"""Game manifest roundtrip."""

import json
from pathlib import Path

from reshade_shader_manager.core.manifest import SCHEMA_VERSION, GameManifest, load_game_manifest, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths, game_id_from_game_dir


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
        plugin_addon_companion_symlinks={"swapchain-override": ["/game/reshade-shaders/Shaders/addons/x/a.fx"]},
    )
    save_game_manifest(paths, m)
    assert paths.game_manifest_path(game_id_from_game_dir(game_dir)).is_file()
    m2 = load_game_manifest(paths, game_dir)
    assert m2 is not None
    assert m2.schema_version == SCHEMA_VERSION
    assert m2.enabled_repo_ids == ["quint"]
    assert m2.symlinks_by_repo_id["quint"] == ["/tmp/a", "/tmp/b"]
    assert m2.enabled_plugin_addon_ids == ["swapchain-override"]
    assert m2.plugin_addon_root_copies["swapchain-override"] == ["swapchain_override.addon64"]
    assert m2.plugin_addon_companion_symlinks["swapchain-override"] == [
        "/game/reshade-shaders/Shaders/addons/x/a.fx"
    ]


def test_manifest_load_schema_v1_migrates_to_v2(tmp_path: Path, monkeypatch) -> None:
    """On-disk schema_version 1 without plugin add-on keys loads as current schema with empty add-on state."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game_dir = (tmp_path / "legacy").resolve()
    game_dir.mkdir()
    gid = game_id_from_game_dir(game_dir)
    mp = paths.game_manifest_path(gid)
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

    save_game_manifest(paths, m)
    data = json.loads(mp.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["enabled_plugin_addon_ids"] == []
    assert data["plugin_addon_root_copies"] == {}
    assert data["plugin_addon_companion_symlinks"] == {}
