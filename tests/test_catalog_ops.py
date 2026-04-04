"""fetch_merged_catalogs wiring."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reshade_shader_manager.core.catalog_ops import fetch_merged_catalogs
from reshade_shader_manager.core.config import AppConfig
from reshade_shader_manager.core.paths import RsmPaths


@patch("reshade_shader_manager.core.catalog_ops.get_upstream_plugin_addons")
@patch("reshade_shader_manager.core.catalog_ops.merged_catalog")
@patch("reshade_shader_manager.core.catalog_ops.get_pcgw_repos")
def test_fetch_merged_catalogs_sequence(
    mock_pcgw: MagicMock,
    mock_merge: MagicMock,
    mock_plugin: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    mock_pcgw.return_value = [{"id": "pcgw", "git_url": "https://x"}]
    mock_merge.return_value = [{"id": "merged", "git_url": "https://y"}]
    mock_plugin.return_value = [{"id": "addon1", "name": "A"}]
    cfg = AppConfig()
    s, p = fetch_merged_catalogs(paths, cfg, force_refresh=False)
    mock_pcgw.assert_called_once()
    mock_merge.assert_called_once_with(paths, mock_pcgw.return_value)
    mock_plugin.assert_called_once()
    assert s == mock_merge.return_value
    assert p == mock_plugin.return_value
