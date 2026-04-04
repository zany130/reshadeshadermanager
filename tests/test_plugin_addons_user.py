"""User plugin_addons.json and merged catalog."""

from pathlib import Path

import pytest

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_parse import assert_plugin_addon_row
from reshade_shader_manager.core.plugin_addons_user import (
    load_user_plugin_addons,
    merged_plugin_addon_catalog,
    save_user_plugin_addons,
    upsert_user_plugin_addon,
)


def test_merged_user_overrides_upstream_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    upstream_id = "same-id-aaaaaaaaaaaa"
    user_row = {
        "id": upstream_id,
        "name": "User override",
        "description": "u",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "https://user.example/x",
        "repository_url": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "user",
    }
    save_user_plugin_addons(paths, [user_row])
    upstream = [
        {
            "id": upstream_id,
            "name": "Upstream",
            "description": "",
            "download_url_32": "",
            "download_url_64": "https://up.example/y",
            "download_url": "",
            "repository_url": "https://github.com/a/a",
            "effect_install_path": "",
            "upstream_section": "01",
            "source": "upstream",
        }
    ]
    merged = merged_plugin_addon_catalog(paths, upstream)
    assert len(merged) == 1
    assert merged[0]["name"] == "User override"
    assert merged[0]["source"] == "user"


def test_user_json_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    rows = [
        {
            "id": "my-addon",
            "name": "My Addon",
            "description": "d",
            "download_url_32": "https://a/a32",
            "download_url_64": "https://a/a64",
            "download_url": "",
            "repository_url": "https://github.com/u/u",
            "effect_install_path": "",
            "upstream_section": "",
            "source": "user",
        }
    ]
    save_user_plugin_addons(paths, rows)
    loaded = load_user_plugin_addons(paths)
    assert len(loaded) == 1
    assert loaded[0]["id"] == "my-addon"


def test_upsert_replaces_same_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    base = {
        "name": "One",
        "description": "",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "https://a/one",
        "repository_url": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "user",
    }
    upsert_user_plugin_addon(paths, {"id": "same", **base})
    upsert_user_plugin_addon(
        paths,
        {
            "id": "same",
            **{**base, "name": "Two", "download_url": "https://a/two"},
        },
    )
    loaded = load_user_plugin_addons(paths)
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Two"
    assert loaded[0]["download_url"] == "https://a/two"


def test_upsert_repo_mode_without_download_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    row = {
        "id": "repo-addon",
        "name": "Repo Addon",
        "description": "",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "https://github.com/x/x.git",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "user",
        "install_mode": "repo",
        "dll_32_path": "x.addon32",
        "dll_64_path": "x.addon64",
        "shader_root": "",
        "companion_shader_paths": "",
    }
    upsert_user_plugin_addon(paths, row)
    loaded = load_user_plugin_addons(paths)
    assert len(loaded) == 1
    assert loaded[0]["install_mode"] == "repo"
    assert loaded[0]["dll_64_path"] == "x.addon64"


def test_upsert_requires_download_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    row = {
        "id": "x",
        "name": "X",
        "description": "",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "https://github.com/a/a",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "user",
    }
    with pytest.raises(ValueError, match="at least one download URL"):
        upsert_user_plugin_addon(paths, row)


def test_repo_mode_requires_paths_and_repo_url() -> None:
    base = {
        "id": "r",
        "name": "R",
        "description": "",
        "download_url_32": "",
        "download_url_64": "",
        "download_url": "",
        "repository_url": "",
        "effect_install_path": "",
        "upstream_section": "",
        "source": "user",
        "install_mode": "repo",
        "dll_32_path": "",
        "dll_64_path": "",
        "shader_root": "",
        "companion_shader_paths": "",
    }
    with pytest.raises(ValueError, match="repository_url"):
        assert_plugin_addon_row({**base, "dll_32_path": "a.addon32"})
    with pytest.raises(ValueError, match="dll_32_path"):
        assert_plugin_addon_row({**base, "repository_url": "https://github.com/a/a.git"})
