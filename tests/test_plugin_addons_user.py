"""User plugin_addons.json and merged catalog."""

from pathlib import Path

import pytest

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_user import (
    load_user_plugin_addons,
    merged_plugin_addon_catalog,
    save_user_plugin_addons,
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
