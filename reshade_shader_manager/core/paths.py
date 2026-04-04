"""XDG paths and stable per-game IDs."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


def _xdg_dir(env_var: str, fallback: Path) -> Path:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return fallback.expanduser().resolve()


@dataclass(frozen=True)
class RsmPaths:
    """Resolved XDG locations for RSM."""

    config_dir: Path
    data_dir: Path
    cache_dir: Path

    @staticmethod
    def from_env() -> RsmPaths:
        home = Path.home()
        config = _xdg_dir("XDG_CONFIG_HOME", home / ".config") / "reshade-shader-manager"
        data = _xdg_dir("XDG_DATA_HOME", home / ".local" / "share") / "reshade-shader-manager"
        cache = _xdg_dir("XDG_CACHE_HOME", home / ".cache") / "reshade-shader-manager"
        return RsmPaths(config_dir=config, data_dir=data, cache_dir=cache)

    def ensure_layout(self) -> None:
        """Create expected base directories."""
        for p in (
            self.config_dir,
            self.config_dir / "games",
            self.data_dir,
            self.data_dir / "repos",
            self.data_dir / "reshade" / "downloads",
            self.data_dir / "reshade" / "extracted",
            self.data_dir / "d3d8to9",
            self.data_dir / "addons" / "downloads",
            self.data_dir / "logs",
            self.cache_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)

    def config_json(self) -> Path:
        return self.config_dir / "config.json"

    def ui_state_json(self) -> Path:
        return self.config_dir / "ui_state.json"

    def repos_json(self) -> Path:
        return self.config_dir / "repos.json"

    def games_dir(self) -> Path:
        return self.config_dir / "games"

    def game_manifest_path(self, game_id: str) -> Path:
        return self.games_dir() / f"{game_id}.json"

    def repo_clone_dir(self, repo_id: str) -> Path:
        return self.data_dir / "repos" / repo_id

    def reshade_download_path(self, version: str, *, addon: bool) -> Path:
        suffix = "_Addon" if addon else ""
        name = f"ReShade_Setup_{version}{suffix}.exe"
        return self.data_dir / "reshade" / "downloads" / name

    def reshade_extract_dir(self, version: str) -> Path:
        return self.data_dir / "reshade" / "extracted" / version

    def pcgw_cache_path(self) -> Path:
        return self.cache_dir / "pcgw_repos.json"

    def plugin_addons_cache_path(self) -> Path:
        return self.cache_dir / "plugin_addons_catalog.json"

    def plugin_addons_json(self) -> Path:
        """User-defined plugin add-ons (not upstream ``Addons.ini``)."""
        return self.config_dir / "plugin_addons.json"

    def plugin_addon_artifact_dir(self, addon_id: str, download_url: str) -> Path:
        """Per-URL download/extract cache for a plugin add-on (under XDG data)."""
        safe_id = re.sub(r"[^a-z0-9_-]+", "_", addon_id.strip().lower())[:48].strip("_") or "addon"
        h = hashlib.sha256(download_url.encode("utf-8")).hexdigest()[:16]
        return self.data_dir / "addons" / "downloads" / safe_id / h

    def reshade_latest_cache_path(self) -> Path:
        return self.cache_dir / "reshade_latest_cache.json"

    def d3d8to9_cached_dll_path(self, *, release_tag: str) -> Path:
        """Cached copy of upstream d3d8to9 ``d3d8.dll`` (``release_tag`` e.g. ``v1.15.1``)."""
        safe = release_tag.lstrip("v").replace("/", "-")
        return self.data_dir / "d3d8to9" / f"d3d8-{safe}.dll"


def game_id_from_game_dir(game_dir: str | Path) -> str:
    """
    Stable opaque ID for a game install root.

    Uses SHA-256 of the canonical absolute path (UTF-8) as hex, so the same
    directory always maps to the same manifest file.
    """
    resolved = Path(game_dir).expanduser().resolve()
    normalized = str(resolved).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def get_paths(*, ensure_layout: bool = True) -> RsmPaths:
    """Default RsmPaths from environment; optionally create base directories."""
    p = RsmPaths.from_env()
    if ensure_layout:
        p.ensure_layout()
    return p
