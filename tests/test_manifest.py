"""Game manifest roundtrip."""

from pathlib import Path

from reshade_shader_manager.core.manifest import GameManifest, load_game_manifest, save_game_manifest
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
    )
    save_game_manifest(paths, m)
    assert paths.game_manifest_path(game_id_from_game_dir(game_dir)).is_file()
    m2 = load_game_manifest(paths, game_dir)
    assert m2 is not None
    assert m2.enabled_repo_ids == ["quint"]
    assert m2.symlinks_by_repo_id["quint"] == ["/tmp/a", "/tmp/b"]
