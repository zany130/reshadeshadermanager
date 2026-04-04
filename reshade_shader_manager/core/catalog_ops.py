"""Fetch merged shader + plugin add-on catalogs (shared by GUI and CLI)."""

from __future__ import annotations

from reshade_shader_manager.core.config import AppConfig
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.pcgw import get_pcgw_repos
from reshade_shader_manager.core.plugin_addons_catalog import get_upstream_plugin_addons
from reshade_shader_manager.core.repos import merged_catalog


def fetch_merged_catalogs(
    paths: RsmPaths,
    cfg: AppConfig,
    *,
    force_refresh: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Return ``(merged_shader_catalog, plugin_addon_catalog)``.

    Same sequence as the GUI catalog loader: PCGW → merged built-in/user/PCGW shader
    repos → official Addons.ini plugin catalog.
    """
    pcgw = get_pcgw_repos(
        paths,
        ttl_hours=cfg.pcgw_cache_ttl_hours,
        force_refresh=force_refresh,
    )
    shader_cat = merged_catalog(paths, pcgw)
    plugin_cat = get_upstream_plugin_addons(
        paths,
        ttl_hours=cfg.plugin_addons_catalog_ttl_hours,
        force_refresh=force_refresh,
    )
    return shader_cat, plugin_cat
