"""Plugin add-on install: ZIP picker, apply, conflicts."""

import io
import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from reshade_shader_manager.core.exceptions import RSMError
from reshade_shader_manager.core.manifest import GameManifest, new_game_manifest
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_install import (
    apply_plugin_addon_installation,
    filter_catalog_installable_for_arch,
    installability_detail,
    pick_payload_from_zip_extract,
    prepare_payload_file,
    resolve_download_url_for_arch,
)


def test_resolve_download_url_prefers_arch_specific() -> None:
    e = {
        "id": "x",
        "name": "X",
        "download_url_32": "https://a/32",
        "download_url_64": "https://a/64",
        "download_url": "https://a/any",
        "repository_url": "",
        "description": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "upstream",
    }
    assert resolve_download_url_for_arch(e, arch="64") == "https://a/64"
    assert resolve_download_url_for_arch(e, arch="32") == "https://a/32"


def test_resolve_download_falls_back_to_single_url() -> None:
    e = {
        "id": "x",
        "name": "X",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "https://a/one.zip",
        "repository_url": "",
        "description": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "upstream",
    }
    assert resolve_download_url_for_arch(e, arch="64") == "https://a/one.zip"


def test_resolve_download_missing_raises() -> None:
    e = {
        "id": "x",
        "name": "X",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "",
        "description": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "upstream",
    }
    with pytest.raises(RSMError, match="no download links"):
        resolve_download_url_for_arch(e, arch="64")


def test_resolve_repository_only_raises() -> None:
    e = {
        "id": "geo",
        "name": "Geo3D",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "https://github.com/Flugan/Geo3D-Installer",
        "description": "",
        "effect_install_path": "",
        "upstream_section": "16",
        "source": "upstream",
    }
    with pytest.raises(RSMError, match="repository-only"):
        resolve_download_url_for_arch(e, arch="64")


def test_installability_detail() -> None:
    e = {
        "id": "x",
        "name": "X",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "https://github.com/a/a",
        "description": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "upstream",
    }
    ok, reason = installability_detail(e, arch="64")
    assert ok is False
    assert "repository-only" in reason


def _entry(
    eid: str,
    *,
    u32: str = "",
    u64: str = "",
    u1: str = "",
    repo: str = "",
) -> dict[str, str]:
    return {
        "id": eid,
        "name": eid,
        "download_url_32": u32,
        "download_url_64": u64,
        "download_url": u1,
        "repository_url": repo,
        "description": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "upstream",
    }


def test_filter_catalog_installable_for_arch_excludes_repo_mode() -> None:
    """Repo-based rows are deferred (install not implemented); filtered from Manage list."""
    repo = {
        "id": "repo-only",
        "name": "R",
        "description": "",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "https://github.com/a/a.git",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "user",
        "install_mode": "repo",
        "dll_32_path": "a.addon32",
        "dll_64_path": "a.addon64",
        "shader_root": "",
        "companion_shader_paths": "",
    }
    assert filter_catalog_installable_for_arch([repo], arch="64") == []


def test_filter_catalog_installable_for_arch() -> None:
    both = _entry("both", u32="https://x/32", u64="https://x/64")
    sixtyfour_only = _entry("64only", u64="https://x/64only")
    repo_only = _entry("repo", repo="https://github.com/a/a")
    cat = [both, sixtyfour_only, repo_only]
    assert [r["id"] for r in filter_catalog_installable_for_arch(cat, arch="32")] == ["both"]
    assert [r["id"] for r in filter_catalog_installable_for_arch(cat, arch="64")] == [
        "both",
        "64only",
    ]


def test_pick_zip_single_addon64(tmp_path: Path) -> None:
    root = tmp_path / "z"
    root.mkdir()
    (root / "plugin.addon64").write_bytes(b"x")
    p = pick_payload_from_zip_extract(root, arch="64")
    assert p.name == "plugin.addon64"


def test_pick_zip_multiple_addon64_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "z"
    root.mkdir()
    (root / "a.addon64").write_bytes(b"a")
    (root / "b.addon64").write_bytes(b"b")
    with pytest.raises(RSMError, match="multiple .addon64"):
        pick_payload_from_zip_extract(root, arch="64")


def test_apply_copies_raw_addon_with_mock_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game = tmp_path / "game"
    game.mkdir()
    payload = tmp_path / "payload.addon32"
    payload.write_bytes(b"fake-addon")
    m = new_game_manifest(game)
    m.reshade_arch = "32"
    cat = {
        "a1": {
            "id": "a1",
            "name": "Test",
            "description": "",
            "download_url_32": "https://example.com/x.addon32",
            "download_url_64": "",
            "download_url": "",
            "repository_url": "",
            "effect_install_path": "",
            "upstream_section": "",
            "source": "upstream",
        }
    }

    def fake_prepare(*_a, **_k):
        return payload, None

    with patch("reshade_shader_manager.core.plugin_addons_install.prepare_payload_file", side_effect=fake_prepare):
        apply_plugin_addon_installation(
            paths=paths,
            manifest=m,
            game_dir=game,
            desired_plugin_addon_ids={"a1"},
            catalog_by_id=cat,
        )

    assert (game / "payload.addon32").is_file()
    assert (game / "payload.addon32").read_bytes() == b"fake-addon"
    assert m.plugin_addon_root_copies["a1"] == ["payload.addon32"]
    assert m.plugin_addon_companion_symlinks["a1"] == []
    assert m.enabled_plugin_addon_ids == ["a1"]


def test_conflict_existing_unmanaged_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game = tmp_path / "game"
    game.mkdir()
    payload = tmp_path / "payload.addon32"
    payload.write_bytes(b"x")
    (game / "payload.addon32").write_text("user file", encoding="utf-8")
    m = new_game_manifest(game)
    m.reshade_arch = "32"
    cat = {
        "a1": {
            "id": "a1",
            "name": "Test",
            "description": "",
            "download_url_32": "https://example.com/x.addon32",
            "download_url_64": "",
            "download_url": "",
            "repository_url": "",
            "effect_install_path": "",
            "upstream_section": "",
            "source": "upstream",
        }
    }

    def fake_prepare(*_a, **_k):
        return payload, None

    with (
        patch("reshade_shader_manager.core.plugin_addons_install.prepare_payload_file", side_effect=fake_prepare),
        pytest.raises(RSMError, match="not managed by RSM"),
    ):
        apply_plugin_addon_installation(
            paths=paths,
            manifest=m,
            game_dir=game,
            desired_plugin_addon_ids={"a1"},
            catalog_by_id=cat,
        )


def test_zip_roundtrip_prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nested/x.addon64", b"fake64")
    zip_bytes = buf.getvalue()
    addon_id = "testaddon"
    url = "https://example.com/blob.zip"

    cache_dir = paths.plugin_addon_artifact_dir(addon_id, url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "blob.zip").write_bytes(zip_bytes)

    p, ex_root = prepare_payload_file(paths, addon_id, url, arch="64")
    assert p.name == "x.addon64"
    assert ex_root is not None
    assert (ex_root / "nested" / "x.addon64").is_file()


def test_apply_zip_creates_companion_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game = tmp_path / "game"
    game.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nested/x.addon64", b"fake64")
        zf.writestr("Shaders/companion.fx", b"// fx\n")
    zip_bytes = buf.getvalue()
    addon_id = "myaddon"
    url = "https://example.com/blob.zip"
    cache_dir = paths.plugin_addon_artifact_dir(addon_id, url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "blob.zip").write_bytes(zip_bytes)

    m = new_game_manifest(game)
    m.reshade_arch = "64"
    cat = {
        "myaddon": {
            "id": "myaddon",
            "name": "Test",
            "description": "",
            "download_url_32": "",
            "download_url_64": "https://example.com/blob.zip",
            "download_url": "",
            "repository_url": "",
            "effect_install_path": "",
            "upstream_section": "",
            "source": "upstream",
        }
    }
    apply_plugin_addon_installation(
        paths=paths,
        manifest=m,
        game_dir=game,
        desired_plugin_addon_ids={"myaddon"},
        catalog_by_id=cat,
    )
    link = game / "reshade-shaders" / "Shaders" / "addons" / "myaddon" / "companion.fx"
    assert link.is_symlink()
    assert m.plugin_addon_root_copies["myaddon"] == ["x.addon64"]
    assert os.path.abspath(link) in m.plugin_addon_companion_symlinks["myaddon"]


def test_remove_addon_drops_companion_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    game = tmp_path / "game"
    game.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nested/x.addon64", b"fake64")
        zf.writestr("Shaders/companion.fx", b"// fx\n")
    cache_dir = paths.plugin_addon_artifact_dir("myaddon", "https://example.com/blob.zip")
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "blob.zip").write_bytes(buf.getvalue())

    m = new_game_manifest(game)
    m.reshade_arch = "64"
    cat = {
        "myaddon": {
            "id": "myaddon",
            "name": "Test",
            "description": "",
            "download_url_32": "",
            "download_url_64": "https://example.com/blob.zip",
            "download_url": "",
            "repository_url": "",
            "effect_install_path": "",
            "upstream_section": "",
            "source": "upstream",
        }
    }
    apply_plugin_addon_installation(
        paths=paths,
        manifest=m,
        game_dir=game,
        desired_plugin_addon_ids={"myaddon"},
        catalog_by_id=cat,
    )
    link = game / "reshade-shaders" / "Shaders" / "addons" / "myaddon" / "companion.fx"
    assert link.is_symlink()

    apply_plugin_addon_installation(
        paths=paths,
        manifest=m,
        game_dir=game,
        desired_plugin_addon_ids=set(),
        catalog_by_id=cat,
    )
    assert not link.exists()
    assert m.plugin_addon_companion_symlinks == {}
