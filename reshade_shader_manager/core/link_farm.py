"""Per-game directory symlinks into global shader clones."""

from __future__ import annotations

import logging
from pathlib import Path

from reshade_shader_manager.core.git_sync import clone_or_pull
from reshade_shader_manager.core.manifest import GameManifest, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths

log = logging.getLogger(__name__)


def _find_subdir_case_insensitive(root: Path, name: str) -> Path | None:
    want = name.lower()
    if not root.is_dir():
        return None
    for child in root.iterdir():
        if child.is_dir() and child.name.lower() == want:
            return child
    return None


def _remove_symlinks(paths: list[str]) -> None:
    for s in paths:
        p = Path(s)
        if p.is_symlink() or p.is_file():
            try:
                p.unlink()
            except OSError as e:
                log.warning("Could not remove %s: %s", p, e)


def _prune_empty_parents(leaf: Path, stop_at: Path) -> None:
    cur = leaf.parent
    while cur.resolve() != stop_at.resolve() and cur.is_dir():
        try:
            next_cur = cur.parent
            if not any(cur.iterdir()):
                cur.rmdir()
            cur = next_cur
        except OSError:
            break


def disable_shader_repo(*, paths: RsmPaths, manifest: GameManifest, repo_id: str) -> None:
    """Remove symlinks recorded for ``repo_id`` and drop it from ``enabled_repo_ids``."""
    rid = repo_id.strip().lower()
    game_dir = Path(manifest.game_dir).resolve()
    links = list(manifest.symlinks_by_repo_id.pop(rid, []))
    _remove_symlinks(links)
    if rid in manifest.enabled_repo_ids:
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
    save_game_manifest(paths, manifest)
    for link in links:
        _prune_empty_parents(Path(link), game_dir)


def enable_shader_repo(
    *,
    paths: RsmPaths,
    manifest: GameManifest,
    repo_id: str,
    git_url: str,
    pull: bool = True,
) -> bool:
    """
    Clone/pull global repo, then symlink ``Shaders/<id>`` and/or ``Textures/<id>``.

    Returns ``True`` if at least one symlink was created. If neither subdirectory
    exists in the clone, logs a warning and returns ``False`` (does not add to
    ``enabled_repo_ids``).
    """
    rid = repo_id.strip().lower()
    clone_dir = paths.repo_clone_dir(rid)
    if pull:
        clone_or_pull(clone_dir, git_url)

    shaders_src = _find_subdir_case_insensitive(clone_dir, "Shaders")
    textures_src = _find_subdir_case_insensitive(clone_dir, "Textures")
    if shaders_src is None and textures_src is None:
        log.warning(
            "Repo %r has neither Shaders nor Textures at clone root — skipping enable",
            rid,
        )
        return False

    game_dir = Path(manifest.game_dir)
    base = game_dir / "reshade-shaders"
    sh_dst_root = base / "Shaders"
    tx_dst_root = base / "Textures"
    sh_dst_root.mkdir(parents=True, exist_ok=True)
    tx_dst_root.mkdir(parents=True, exist_ok=True)

    # Drop prior symlinks for this repo (do not save until new projection succeeds or we finalize failure).
    old_links = list(manifest.symlinks_by_repo_id.pop(rid, []))
    _remove_symlinks(old_links)

    new_links: list[str] = []
    if shaders_src is not None:
        target = shaders_src.resolve()
        link = sh_dst_root / rid
        if link.exists() and not link.is_symlink():
            log.warning("Refusing to overwrite non-symlink %s", link)
        else:
            if link.is_symlink() or link.exists():
                link.unlink(missing_ok=True)
            link.symlink_to(target, target_is_directory=True)
            # Record the symlink path itself (do not resolve through the link — targets are for unlink).
            new_links.append(str(link.absolute()))

    if textures_src is not None:
        target = textures_src.resolve()
        link = tx_dst_root / rid
        if link.exists() and not link.is_symlink():
            log.warning("Refusing to overwrite non-symlink %s", link)
        else:
            if link.is_symlink() or link.exists():
                link.unlink(missing_ok=True)
            link.symlink_to(target, target_is_directory=True)
            # Record the symlink path itself (do not resolve through the link — targets are for unlink).
            new_links.append(str(link.absolute()))

    if not new_links:
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
        save_game_manifest(paths, manifest)
        for link in old_links:
            _prune_empty_parents(Path(link), game_dir.resolve())
        return False

    manifest.symlinks_by_repo_id[rid] = new_links
    if rid not in manifest.enabled_repo_ids:
        manifest.enabled_repo_ids.append(rid)
    save_game_manifest(paths, manifest)
    gd = game_dir.resolve()
    for link in old_links:
        _prune_empty_parents(Path(link), gd)
    return True
