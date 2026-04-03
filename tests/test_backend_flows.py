"""
End-to-end backend flow tests (no GTK).

Uses a fake ReShade zip and mocked ``git clone`` data so tests stay offline by default.
Set ``RSM_NETWORK_TEST=1`` to run optional PCGW live fetch.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

from reshade_shader_manager.core import reshade as reshade_mod
from reshade_shader_manager.core.ini import DEFAULT_EFFECT_SEARCH, DEFAULT_TEXTURE_SEARCH
import shutil

from reshade_shader_manager.core.link_farm import (
    apply_shader_projection,
    disable_shader_repo,
    enable_shader_repo,
    unlink_recorded_projection_path,
)
from reshade_shader_manager.core.manifest import GameManifest, load_game_manifest, new_game_manifest
from reshade_shader_manager.core.pcgw import fetch_pcgw_repos_raw, parse_pcgw_repos_from_html
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.reshade import install_reshade, remove_reshade_binaries


def _minimal_reshade_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ReShade64.dll", b"MZ" + b"\0" * 120)
        zf.writestr("ReShade32.dll", b"MZ" + b"\0" * 120)
        zf.writestr("nested/x/ReShade64.dll", b"MZnested")
        zf.writestr("d3dcompiler_47.dll", b"compiler")
    return buf.getvalue()


@pytest.fixture
def fake_download(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake(version: str, paths: RsmPaths, *, addon: bool) -> Path:
        dest = paths.reshade_download_path(version, addon=addon)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_minimal_reshade_zip_bytes())
        return dest

    monkeypatch.setattr(reshade_mod, "download_reshade_installer", _fake)


@pytest.fixture
def fake_git_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate clone dir with standard Shaders/ + Textures/ (no real git)."""

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "Shaders").mkdir(exist_ok=True)
        (repo_dir / "Textures").mkdir(exist_ok=True)
        (repo_dir / "Shaders" / "test.fx").write_text("//x", encoding="utf-8")
        (repo_dir / "Textures" / "t.png").write_bytes(b"\x89PNG\r\n")

    monkeypatch.setattr("reshade_shader_manager.core.link_farm.clone_or_pull", _fake)


@pytest.fixture
def fake_git_repo_nested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clone root has no Shaders/; nested folder holds .fx directly."""

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        repo_dir.mkdir(parents=True, exist_ok=True)
        nested = repo_dir / "pack" / "glsl"
        nested.mkdir(parents=True)
        (nested / "effect.fx").write_text("//nested", encoding="utf-8")

    monkeypatch.setattr("reshade_shader_manager.core.link_farm.clone_or_pull", _fake)


@pytest.fixture
def fake_git_repo_flat_fx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only loose .fx at clone root (file fallback)."""

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "root.fx").write_text("//root", encoding="utf-8")

    monkeypatch.setattr("reshade_shader_manager.core.link_farm.clone_or_pull", _fake)


def test_install_remove_reshade_flow(
    tmp_path: Path, rsm_paths: RsmPaths, fake_download: None
) -> None:
    game = tmp_path / "game_root"
    game.mkdir(parents=True)
    m = new_game_manifest(game)
    m.reshade_arch = "64"
    install_reshade(
        paths=rsm_paths,
        manifest=m,
        graphics_api="dx11",
        reshade_version="9.9.9-test",
        variant="standard",
        create_ini_if_missing=True,
    )
    m2 = load_game_manifest(rsm_paths, game)
    assert m2 is not None
    assert m2.installed_reshade_files == ["dxgi.dll", "d3dcompiler_47.dll"]
    assert (game / "dxgi.dll").is_file()
    assert (game / "d3dcompiler_47.dll").is_file()
    ini = (game / "ReShade.ini").read_text(encoding="utf-8")
    assert DEFAULT_EFFECT_SEARCH in ini
    assert DEFAULT_TEXTURE_SEARCH in ini

    warn = remove_reshade_binaries(paths=rsm_paths, manifest=m2)
    assert warn == []
    m3 = load_game_manifest(rsm_paths, game)
    assert m3 is not None
    assert m3.installed_reshade_files == []
    assert not (game / "dxgi.dll").exists()
    assert (game / "ReShade.ini").is_file()


def test_reinstall_replaces_proxy_and_manifest_list(
    tmp_path: Path, rsm_paths: RsmPaths, fake_download: None
) -> None:
    """v0.1: second install removes prior tracked DLLs and replaces manifest list."""
    game = tmp_path / "game_switch"
    game.mkdir(parents=True)
    m = new_game_manifest(game)
    m.reshade_arch = "64"
    install_reshade(
        paths=rsm_paths,
        manifest=m,
        graphics_api="dx11",
        reshade_version="9.9.9-a",
        variant="standard",
        create_ini_if_missing=True,
    )
    assert (game / "dxgi.dll").is_file()
    m_reload = load_game_manifest(rsm_paths, game)
    assert m_reload is not None
    install_reshade(
        paths=rsm_paths,
        manifest=m_reload,
        graphics_api="opengl",
        reshade_version="9.9.9-b",
        variant="standard",
        create_ini_if_missing=True,
    )
    assert not (game / "dxgi.dll").exists()
    assert (game / "opengl32.dll").is_file()
    m2 = load_game_manifest(rsm_paths, game)
    assert m2 is not None
    assert m2.installed_reshade_files == ["opengl32.dll", "d3dcompiler_47.dll"]


def test_apply_rebuild_recreates_symlinks_after_manual_delete(
    tmp_path: Path, rsm_paths: RsmPaths, fake_git_repo: None
) -> None:
    """Apply always rebuilds from metadata + clone; survives deleted reshade-shaders tree."""
    game = tmp_path / "game_reapply"
    game.mkdir(parents=True)
    cat = {"testrepo": {"id": "testrepo", "git_url": "https://example.com/none.git"}}
    apply_shader_projection(
        paths=rsm_paths,
        game_dir=game,
        desired_repo_ids={"testrepo"},
        catalog_by_id=cat,
        git_pull=True,
    )
    m1 = load_game_manifest(rsm_paths, game)
    assert m1 is not None
    links_before = list(m1.symlinks_by_repo_id.get("testrepo", []))
    assert links_before
    assert (game / "reshade-shaders" / "Shaders" / "testrepo" / "test.fx").is_file()

    shutil.rmtree(game / "reshade-shaders")
    for lp in links_before:
        assert not Path(lp).exists()

    apply_shader_projection(
        paths=rsm_paths,
        game_dir=game,
        desired_repo_ids={"testrepo"},
        catalog_by_id=cat,
        git_pull=False,
    )
    m2 = load_game_manifest(rsm_paths, game)
    assert m2 is not None
    assert "testrepo" in m2.enabled_repo_ids
    assert (game / "reshade-shaders" / "Shaders" / "testrepo" / "test.fx").is_file()


def test_enable_nested_shader_directory(tmp_path: Path, rsm_paths: RsmPaths, fake_git_repo_nested: None) -> None:
    game = tmp_path / "game_nested"
    game.mkdir(parents=True)
    m = new_game_manifest(game)
    ok = enable_shader_repo(
        paths=rsm_paths,
        manifest=m,
        repo_id="nested",
        git_url="https://example.com/nested.git",
        git_pull=True,
    )
    assert ok is True
    assert (game / "reshade-shaders" / "Shaders" / "nested" / "effect.fx").is_file()
    m2 = load_game_manifest(rsm_paths, game)
    assert m2 is not None
    assert "nested" in m2.enabled_repo_ids


def test_enable_flat_fx_file_fallback(tmp_path: Path, rsm_paths: RsmPaths, fake_git_repo_flat_fx: None) -> None:
    game = tmp_path / "game_flat"
    game.mkdir(parents=True)
    m = new_game_manifest(game)
    ok = enable_shader_repo(
        paths=rsm_paths,
        manifest=m,
        repo_id="flatty",
        git_url="https://example.com/flat.git",
        git_pull=True,
    )
    assert ok is True
    p = game / "reshade-shaders" / "Shaders" / "flatty" / "root.fx"
    assert p.is_symlink()
    assert p.read_text(encoding="utf-8") == "//root"


def test_unlink_recorded_skips_non_symlink(tmp_path: Path) -> None:
    game = tmp_path / "g"
    (game / "reshade-shaders" / "Shaders" / "r").mkdir(parents=True)
    p = game / "reshade-shaders" / "Shaders" / "r" / "real.fx"
    p.write_text("//x", encoding="utf-8")
    unlink_recorded_projection_path(game.resolve(), p)
    assert p.is_file()


def test_enable_disable_shader_repo(tmp_path: Path, rsm_paths: RsmPaths, fake_git_repo: None) -> None:
    game = tmp_path / "game_shaders"
    game.mkdir(parents=True)
    m = new_game_manifest(game)
    m.reshade_arch = "64"
    ok = enable_shader_repo(
        paths=rsm_paths,
        manifest=m,
        repo_id="testrepo",
        git_url="https://example.com/none.git",
        git_pull=True,
    )
    assert ok is True
    m2 = load_game_manifest(rsm_paths, game)
    assert m2 is not None
    assert "testrepo" in m2.enabled_repo_ids
    assert "testrepo" in m2.symlinks_by_repo_id
    links = m2.symlinks_by_repo_id["testrepo"]
    assert len(links) == 2
    for lp in links:
        p = Path(lp)
        assert p.is_symlink()
        assert p.resolve().is_dir()
    assert (game / "reshade-shaders" / "Shaders" / "testrepo" / "test.fx").is_file()

    disable_shader_repo(paths=rsm_paths, manifest=m2, repo_id="testrepo")
    m3 = load_game_manifest(rsm_paths, game)
    assert m3 is not None
    assert "testrepo" not in m3.enabled_repo_ids
    assert "testrepo" not in m3.symlinks_by_repo_id
    for lp in links:
        assert not Path(lp).exists()


def test_pcgw_parse_fixture() -> None:
    html = (Path(__file__).parent / "fixtures" / "pcgw_sample.html").read_text(encoding="utf-8")
    repos = parse_pcgw_repos_from_html(html)
    ids = {r["id"] for r in repos}
    assert "quint" in ids
    assert "reshade-shaders" in ids
    quint = next(r for r in repos if r["id"] == "quint")
    assert quint["source"] == "pcgw"
    assert quint["git_url"] == "https://github.com/martymcmodding/qUINT.git"
    assert quint["name"] == "qUINT"


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RSM_NETWORK_TEST") != "1",
    reason="set RSM_NETWORK_TEST=1 to hit PCGW + GitHub",
)
def test_pcgw_fetch_live() -> None:
    repos, err = fetch_pcgw_repos_raw()
    assert err is None, err
    assert isinstance(repos, list)
    assert len(repos) >= 1
    assert all(r.get("source") == "pcgw" for r in repos)
    assert all("git_url" in r and "id" in r for r in repos)


def test_remove_reshade_leaves_shaders_and_enabled(
    tmp_path: Path, rsm_paths: RsmPaths, fake_download: None, fake_git_repo: None
) -> None:
    """Locked behavior: remove binaries does not clear symlinks or enabled_repo_ids."""
    game = tmp_path / "game_mixed"
    game.mkdir(parents=True)
    m = new_game_manifest(game)
    m.reshade_arch = "64"
    install_reshade(
        paths=rsm_paths,
        manifest=m,
        graphics_api="dx11",
        reshade_version="9.9.9-m",
        variant="standard",
        create_ini_if_missing=True,
    )
    m_loaded = load_game_manifest(rsm_paths, game)
    assert m_loaded is not None
    enable_shader_repo(
        paths=rsm_paths,
        manifest=m_loaded,
        repo_id="keepme",
        git_url="https://example.com/x.git",
        git_pull=True,
    )
    m2 = load_game_manifest(rsm_paths, game)
    assert m2 is not None
    symlinks_before = dict(m2.symlinks_by_repo_id)
    enabled_before = list(m2.enabled_repo_ids)
    remove_reshade_binaries(paths=rsm_paths, manifest=m2)
    m3 = load_game_manifest(rsm_paths, game)
    assert m3 is not None
    assert m3.symlinks_by_repo_id == symlinks_before
    assert m3.enabled_repo_ids == enabled_before
    assert m3.installed_reshade_files == []
