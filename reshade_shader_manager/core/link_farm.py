"""Per-game shader projection: symlinks from global clones into the game tree."""

from __future__ import annotations

import logging
from pathlib import Path

from reshade_shader_manager.core.git_sync import clone_or_pull
from reshade_shader_manager.core.manifest import GameManifest, load_game_manifest, new_game_manifest, save_game_manifest
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


def _is_under_managed_reshade_shaders(game_dir: Path, path: Path) -> bool:
    """
    True if ``path`` lies under ``<game_dir>/reshade-shaders``.

    Uses :meth:`pathlib.Path.absolute` for the candidate (not :meth:`~pathlib.Path.resolve`)
    so symlink *locations* in the game tree are not followed into global clone targets.
    """
    try:
        game_abs = game_dir.resolve()
    except OSError:
        return False
    base = (game_abs / "reshade-shaders").absolute()
    try:
        candidate = path.absolute()
    except OSError:
        return False
    if candidate == base:
        return True
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def unlink_recorded_projection_path(game_dir: Path, recorded: Path) -> None:
    """
    Remove a single managed projection path recorded in metadata.

    Only paths under ``<game>/reshade-shaders/`` are touched. Symlinks are removed;
    non-symlink files or directories are left in place with a warning.
    """
    if not _is_under_managed_reshade_shaders(game_dir, recorded):
        log.warning(
            "Recorded path %s is outside managed reshade-shaders tree; not removing",
            recorded,
        )
        return
    p = recorded
    if p.is_symlink():
        try:
            p.unlink()
        except OSError as e:
            log.warning("Could not remove symlink %s: %s", p, e)
    elif p.exists():
        log.warning(
            "Recorded path %s exists but is not a symlink; not removing automatically",
            p,
        )


def _prune_empty_parents(leaf: Path, stop_at: Path) -> None:
    cur = leaf.parent
    try:
        stop_resolved = stop_at.resolve()
    except OSError:
        stop_resolved = stop_at
    while True:
        try:
            cur_resolved = cur.resolve()
        except OSError:
            break
        if cur_resolved == stop_resolved:
            break
        if not cur.is_dir():
            break
        try:
            next_cur = cur.parent
            if not any(cur.iterdir()):
                cur.rmdir()
            cur = next_cur
        except OSError:
            break


def _symlink_dir_or_skip(link: Path, target: Path, *, repo_id: str) -> bool:
    if link.exists() and not link.is_symlink():
        log.warning("Refusing to overwrite non-symlink %s", link)
        return False
    if link.is_symlink() or link.exists():
        link.unlink(missing_ok=True)
    link.symlink_to(target.resolve(), target_is_directory=True)
    log.debug("Symlink %s -> %s", link, target)
    return True


def disable_shader_repo(*, paths: RsmPaths, manifest: GameManifest, repo_id: str) -> None:
    """Remove symlinks recorded for ``repo_id`` and drop it from ``enabled_repo_ids``."""
    rid = repo_id.strip().lower()
    game_dir = Path(manifest.game_dir).resolve()
    links = list(manifest.symlinks_by_repo_id.pop(rid, []))
    for s in links:
        unlink_recorded_projection_path(game_dir, Path(s))
    if rid in manifest.enabled_repo_ids:
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
    save_game_manifest(paths, manifest)
    for link in links:
        _prune_empty_parents(Path(link), game_dir)


def apply_shader_projection(
    *,
    paths: RsmPaths,
    game_dir: Path,
    desired_repo_ids: set[str],
    catalog_by_id: dict[str, dict[str, str]],
    git_pull: bool,
) -> None:
    """
    Rebuild shader projection for ``game_dir`` to match ``desired_repo_ids``.

    Removes **only** symlink paths currently recorded in the manifest (under
    ``reshade-shaders``), prunes empty directories, then recreates projection
    for each desired repo. Does not run ``git pull`` when ``git_pull`` is False
    (existing clones are reused; missing clones are still cloned).
    """
    m = load_game_manifest(paths, game_dir) or new_game_manifest(game_dir)
    gd = Path(m.game_dir).resolve()

    recorded: list[str] = []
    for plist in m.symlinks_by_repo_id.values():
        recorded.extend(plist)
    for s in dict.fromkeys(recorded):
        unlink_recorded_projection_path(gd, Path(s))
    for s in dict.fromkeys(recorded):
        _prune_empty_parents(Path(s), gd)

    m.symlinks_by_repo_id.clear()
    m.enabled_repo_ids.clear()
    save_game_manifest(paths, m)

    for rid in sorted(desired_repo_ids):
        if rid not in catalog_by_id:
            log.warning("Unknown repo id %r — skipped", rid)
            continue
        url = catalog_by_id[rid]["git_url"]
        enable_shader_repo(
            paths=paths,
            manifest=m,
            repo_id=rid,
            git_url=url,
            git_pull=git_pull,
        )


def enable_shader_repo(
    *,
    paths: RsmPaths,
    manifest: GameManifest,
    repo_id: str,
    git_url: str,
    git_pull: bool = True,
) -> bool:
    """
    Clone or update global repo, then project into ``reshade-shaders``.

    Standard layout only: ``Shaders`` and/or ``Textures`` at clone root
    (case-insensitive). Returns ``False`` if neither exists.
    """
    rid = repo_id.strip().lower()
    clone_dir = paths.repo_clone_dir(rid)
    clone_or_pull(clone_dir, git_url, pull=git_pull)

    game_dir = Path(manifest.game_dir)
    gd = game_dir.resolve()
    base = game_dir / "reshade-shaders"
    sh_dst_root = base / "Shaders"
    tx_dst_root = base / "Textures"
    sh_dst_root.mkdir(parents=True, exist_ok=True)
    tx_dst_root.mkdir(parents=True, exist_ok=True)

    old_links = list(manifest.symlinks_by_repo_id.pop(rid, []))
    for s in old_links:
        unlink_recorded_projection_path(gd, Path(s))
    for s in old_links:
        _prune_empty_parents(Path(s), gd)

    new_links: list[str] = []

    shaders_src = _find_subdir_case_insensitive(clone_dir, "Shaders")
    textures_src = _find_subdir_case_insensitive(clone_dir, "Textures")
    if shaders_src is None and textures_src is None:
        log.warning(
            "Repo %r has neither Shaders nor Textures at clone root — skipping enable",
            rid,
        )
        manifest.symlinks_by_repo_id.pop(rid, None)
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
        save_game_manifest(paths, manifest)
        for link in old_links:
            _prune_empty_parents(Path(link), gd)
        return False

    if shaders_src is not None:
        link = sh_dst_root / rid
        if _symlink_dir_or_skip(link, shaders_src, repo_id=rid):
            new_links.append(str(link.absolute()))
    if textures_src is not None:
        link = tx_dst_root / rid
        if _symlink_dir_or_skip(link, textures_src, repo_id=rid):
            new_links.append(str(link.absolute()))

    if not new_links:
        manifest.symlinks_by_repo_id.pop(rid, None)
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
        save_game_manifest(paths, manifest)
        for link in old_links:
            _prune_empty_parents(Path(link), gd)
        return False

    manifest.symlinks_by_repo_id[rid] = new_links
    if rid not in manifest.enabled_repo_ids:
        manifest.enabled_repo_ids.append(rid)
    save_game_manifest(paths, manifest)
    for link in old_links:
        _prune_empty_parents(Path(link), gd)
    return True
