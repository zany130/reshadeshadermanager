"""Backend core: paths, config, manifests, ReShade I/O, repos, git, symlinks."""

from reshade_shader_manager.core.exceptions import RSMError, VersionResolutionError
from reshade_shader_manager.core.paths import RsmPaths, game_id_from_game_dir, get_paths

__all__ = [
    "RSMError",
    "VersionResolutionError",
    "RsmPaths",
    "game_id_from_game_dir",
    "get_paths",
]

# UI and scripts should import submodules explicitly, e.g.:
#   reshade_shader_manager.core.reshade / .link_farm / .repos / .pcgw / .config / .manifest
