"""Per-game manifest JSON (metadata is source of truth)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

from reshade_shader_manager.core.paths import (
    RsmPaths,
    candidate_game_manifest_paths,
    game_dir_fingerprint8,
    legacy_game_manifest_path,
    new_manifest_path_for_game,
)

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# v0.2+: plugin add-ons (DLLs / optional companion shaders) — not ReShade's installer "addon" variant
# (see ``reshade_variant`` / ``VALID_VARIANTS``).

VALID_GRAPHICS_APIS = frozenset({"opengl", "dx8", "dx9", "dx10", "dx11", "dx12"})
VALID_VARIANTS = frozenset({"standard", "addon"})
VALID_ARCH = frozenset({"32", "64"})


@dataclass
class GameManifest:
    schema_version: int = SCHEMA_VERSION
    game_dir: str = ""
    game_exe: str | None = None
    graphics_api: str = "dx11"
    reshade_version: str = ""
    reshade_variant: str = "standard"
    reshade_arch: str = "64"
    enabled_repo_ids: list[str] = field(default_factory=list)
    installed_reshade_files: list[str] = field(default_factory=list)
    symlinks_by_repo_id: dict[str, list[str]] = field(default_factory=dict)
    # Plugin add-ons: official Addons.ini catalog; install state (root copies + companion symlinks).
    enabled_plugin_addon_ids: list[str] = field(default_factory=list)
    plugin_addon_root_copies: dict[str, list[str]] = field(default_factory=dict)
    plugin_addon_companion_symlinks: dict[str, list[str]] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version!r}")
        if self.graphics_api not in VALID_GRAPHICS_APIS:
            raise ValueError(f"invalid graphics_api: {self.graphics_api!r}")
        if self.reshade_variant not in VALID_VARIANTS:
            raise ValueError(f"invalid reshade_variant: {self.reshade_variant!r}")
        if self.reshade_arch not in VALID_ARCH:
            raise ValueError(f"invalid reshade_arch: {self.reshade_arch!r}")
        if not self.game_dir:
            raise ValueError("game_dir is required")

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # normalize symlink map: repo_id -> sorted list for stable JSON
        d["symlinks_by_repo_id"] = {
            k: list(v) for k, v in sorted(self.symlinks_by_repo_id.items(), key=lambda kv: kv[0])
        }
        d["enabled_repo_ids"] = sorted(set(self.enabled_repo_ids))
        d["enabled_plugin_addon_ids"] = sorted(set(self.enabled_plugin_addon_ids))
        d["plugin_addon_root_copies"] = {
            k: list(v) for k, v in sorted(self.plugin_addon_root_copies.items(), key=lambda kv: kv[0])
        }
        d["plugin_addon_companion_symlinks"] = {
            k: list(v)
            for k, v in sorted(self.plugin_addon_companion_symlinks.items(), key=lambda kv: kv[0])
        }
        return d

    @staticmethod
    def from_mapping(m: Mapping[str, Any]) -> GameManifest:
        allowed = {f.name for f in fields(GameManifest)}
        extra = set(m.keys()) - allowed
        if extra:
            raise ValueError(f"unknown manifest keys: {sorted(extra)}")
        sym = m.get("symlinks_by_repo_id", {})
        if not isinstance(sym, dict):
            raise ValueError("symlinks_by_repo_id must be an object")
        sym_clean: dict[str, list[str]] = {}
        for k, v in sym.items():
            if not isinstance(k, str):
                raise ValueError("symlinks_by_repo_id keys must be strings")
            if not isinstance(v, list):
                raise ValueError(f"symlinks_by_repo_id[{k!r}] must be a list")
            sym_clean[k] = [str(x) for x in v]

        def _str_list_dict(key: str) -> dict[str, list[str]]:
            raw = m.get(key, {})
            if not isinstance(raw, dict):
                raise ValueError(f"{key} must be an object")
            out: dict[str, list[str]] = {}
            for k, v in raw.items():
                if not isinstance(k, str):
                    raise ValueError(f"{key} keys must be strings")
                if not isinstance(v, list):
                    raise ValueError(f"{key}[{k!r}] must be a list")
                out[k] = [str(x) for x in v]
            return out

        par = _str_list_dict("plugin_addon_root_copies")
        pac = _str_list_dict("plugin_addon_companion_symlinks")

        file_sv = int(m.get("schema_version", SCHEMA_VERSION))
        if file_sv > SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {file_sv!r}")

        exe = m.get("game_exe")
        return GameManifest(
            schema_version=SCHEMA_VERSION,
            game_dir=str(m.get("game_dir", "")),
            game_exe=None if exe is None else str(exe),
            graphics_api=str(m.get("graphics_api", "dx11")),
            reshade_version=str(m.get("reshade_version", "")),
            reshade_variant=str(m.get("reshade_variant", "standard")),
            reshade_arch=str(m.get("reshade_arch", "64")),
            enabled_repo_ids=[str(x) for x in m.get("enabled_repo_ids", [])],
            installed_reshade_files=[str(x) for x in m.get("installed_reshade_files", [])],
            symlinks_by_repo_id=sym_clean,
            enabled_plugin_addon_ids=[str(x) for x in m.get("enabled_plugin_addon_ids", [])],
            plugin_addon_root_copies=par,
            plugin_addon_companion_symlinks=pac,
        )


def manifest_path_for_game_dir(paths: RsmPaths, game_dir: str | Path) -> Path:
    """Preferred human-readable path ``{slug}-{fp8}.json`` (exe unknown; uses directory basename)."""
    return new_manifest_path_for_game(paths, game_dir, None)


def _canonical_game_dir_str(game_dir: str | Path) -> str:
    return str(Path(game_dir).expanduser().resolve())


def _write_manifest_atomic(paths: RsmPaths, manifest: GameManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest.to_json_dict(), f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def _migrate_legacy_manifest(
    paths: RsmPaths,
    manifest: GameManifest,
    legacy_path: Path,
) -> None:
    target = new_manifest_path_for_game(paths, manifest.game_dir, manifest.game_exe)
    if legacy_path.resolve() == target.resolve():
        return
    _write_manifest_atomic(paths, manifest, target)
    try:
        legacy_path.unlink()
    except OSError as e:
        log.warning("Could not remove legacy manifest %s: %s", legacy_path, e)


def load_game_manifest(
    paths: RsmPaths,
    game_dir: str | Path,
    game_exe: str | None = None,
) -> GameManifest | None:
    """
    Load manifest for ``game_dir``, trying human-readable paths and legacy hash name.

    Lazy migration: if the only match is the legacy ``{sha256}.json``, load and migrate
    to ``{slug}-{fp8}.json`` after a successful write to the new path.
    """
    cgd = _canonical_game_dir_str(game_dir)
    for path in candidate_game_manifest_paths(paths, game_dir, game_exe):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeError) as e:
            log.warning("Could not read manifest %s: %s", path, e)
            continue
        if not isinstance(data, dict):
            continue
        try:
            file_gd = _canonical_game_dir_str(data.get("game_dir", ""))
        except OSError:
            continue
        if file_gd != cgd:
            log.warning("Skipping manifest %s: game_dir does not match this game", path)
            continue
        try:
            m = GameManifest.from_mapping(data)
            m.validate()
        except ValueError as e:
            log.warning("Invalid manifest %s: %s", path, e)
            continue

        if path.resolve() == legacy_game_manifest_path(paths, game_dir).resolve():
            _migrate_legacy_manifest(paths, m, path)
        return m
    return None


def save_game_manifest(paths: RsmPaths, manifest: GameManifest) -> None:
    manifest.validate()
    cgd = _canonical_game_dir_str(manifest.game_dir)
    target = new_manifest_path_for_game(paths, cgd, manifest.game_exe)
    fp8 = game_dir_fingerprint8(cgd)
    leg = legacy_game_manifest_path(paths, cgd)

    _write_manifest_atomic(paths, manifest, target)

    games = paths.games_dir()
    if games.is_dir():
        for p in games.glob(f"*-{fp8}.json"):
            if p.resolve() != target.resolve():
                try:
                    p.unlink()
                except OSError as e:
                    log.warning("Could not remove old manifest %s: %s", p, e)
    if leg.is_file() and leg.resolve() != target.resolve():
        try:
            leg.unlink()
        except OSError as e:
            log.warning("Could not remove legacy manifest %s: %s", leg, e)


def new_game_manifest(game_dir: str | Path, *, game_exe: str | None = None) -> GameManifest:
    gd = str(Path(game_dir).expanduser().resolve())
    return GameManifest(
        game_dir=gd,
        game_exe=None if game_exe is None else str(Path(game_exe).expanduser().resolve()),
    )
