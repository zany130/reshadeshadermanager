"""Plugin add-on upstream fetch and cache."""

from pathlib import Path
from unittest.mock import patch

import pytest

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_catalog import (
    cache_is_fresh,
    get_upstream_plugin_addons,
    load_plugin_addons_cache,
    save_plugin_addons_cache,
)

from tests.test_plugin_addons_parse import SAMPLE_INI


def test_get_upstream_parses_on_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()

    with patch(
        "reshade_shader_manager.core.plugin_addons_catalog.fetch_addons_ini_raw",
        return_value=(SAMPLE_INI, None),
    ):
        rows = get_upstream_plugin_addons(paths, ttl_hours=24.0, force_refresh=True)

    assert len(rows) >= 2
    names = {r["name"] for r in rows}
    assert any("FreePIE" in n for n in names)
    data = load_plugin_addons_cache(paths.plugin_addons_cache_path())
    assert data and isinstance(data.get("addons"), list)


def test_stale_cache_used_when_fetch_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    cache_path = paths.plugin_addons_cache_path()
    save_plugin_addons_cache(
        cache_path,
        [{"id": "keep-me", "name": "X", "description": "", "download_url_32": "", "download_url_64": "", "download_url": "", "repository_url": "", "effect_install_path": "", "upstream_section": "99", "source": "upstream"}],
        None,
    )

    with patch(
        "reshade_shader_manager.core.plugin_addons_catalog.fetch_addons_ini_raw",
        return_value=(None, "network down"),
    ):
        rows = get_upstream_plugin_addons(paths, ttl_hours=0.0, force_refresh=True)

    assert len(rows) == 1
    assert rows[0]["id"] == "keep-me"


def test_cache_is_fresh_respects_ttl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    save_plugin_addons_cache(paths.plugin_addons_cache_path(), [], None)
    assert cache_is_fresh(paths.plugin_addons_cache_path(), ttl_hours=24.0)
    assert not cache_is_fresh(paths.plugin_addons_cache_path(), ttl_hours=0.0)
