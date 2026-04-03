"""Per-game shader projection: symlinks from global clones into the game tree."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from reshade_shader_manager.core.git_sync import clone_or_pull
from reshade_shader_manager.core.manifest import GameManifest, load_game_manifest, new_game_manifest, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths

log = logging.getLogger(__name__)

_SHADER_EXTS = {".fx", ".fxh"}
_TEXTURE_EXTS = {".png", ".jpg", ".jpeg", ".dds", ".tga", ".bmp", ".hdr", ".exr"}


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


def _iter_clone_dirs(clone_root: Path) -> list[Path]:
    """All directories under clone_root except ``.git`` subtrees."""
    out: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(clone_root, topdown=True):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        out.append(Path(dirpath))
    return out


def _dir_has_shader_files_direct(d: Path) -> bool:
    if not d.is_dir():
        return False
    try:
        for c in d.iterdir():
            if c.is_file() and c.suffix.lower() in _SHADER_EXTS:
                return True
    except OSError:
        return False
    return False


def _dir_has_texture_files_direct(d: Path) -> bool:
    if not d.is_dir():
        return False
    try:
        for c in d.iterdir():
            if c.is_file() and c.suffix.lower() in _TEXTURE_EXTS:
                return True
    except OSError:
        return False
    return False


def _discover_nested_shader_roots(clone_dir: Path) -> list[Path]:
    roots: list[Path] = []
    clone_resolved = clone_dir.resolve()
    for d in _iter_clone_dirs(clone_dir):
        if d.resolve() == clone_resolved:
            continue
        if _dir_has_shader_files_direct(d):
            roots.append(d)
    roots.sort(key=lambda p: str(p).lower())
    return roots


def _discover_nested_texture_roots(clone_dir: Path) -> list[Path]:
    roots: list[Path] = []
    clone_resolved = clone_dir.resolve()
    for d in _iter_clone_dirs(clone_dir):
        if d.resolve() == clone_resolved:
            continue
        if _dir_has_texture_files_direct(d) and not _dir_has_shader_files_direct(d):
            roots.append(d)
    roots.sort(key=lambda p: str(p).lower())
    return roots


def _collect_shader_files_for_fallback(clone_dir: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(clone_dir, topdown=True):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            suf = Path(fn).suffix.lower()
            if suf in _SHADER_EXTS:
                files.append(Path(dirpath) / fn)
    files.sort(key=lambda p: str(p).lower())
    return files


def _collect_texture_files_for_fallback(clone_dir: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(clone_dir, topdown=True):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            suf = Path(fn).suffix.lower()
            if suf in _TEXTURE_EXTS:
                files.append(Path(dirpath) / fn)
    files.sort(key=lambda p: str(p).lower())
    return files


def _tree_has_shader_files(root: Path | None) -> bool:
    if root is None or not root.is_dir():
        return False
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            if Path(fn).suffix.lower() in _SHADER_EXTS:
                return True
    return False


def _tree_has_texture_files(root: Path | None) -> bool:
    if root is None or not root.is_dir():
        return False
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            if Path(fn).suffix.lower() in _TEXTURE_EXTS:
                return True
    return False


def _symlink_dir_or_skip(link: Path, target: Path, *, repo_id: str) -> bool:
    if link.exists() and not link.is_symlink():
        log.warning("Refusing to overwrite non-symlink %s", link)
        return False
    if link.is_symlink() or link.exists():
        link.unlink(missing_ok=True)
    # Nested multi-root layout uses e.g. Shaders/<repo>/<subdir>; parents must exist.
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target.resolve(), target_is_directory=True)
    log.debug("Symlink %s -> %s", link, target)
    return True


def _symlink_file_or_skip(link: Path, src: Path, *, repo_id: str) -> bool:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() and not link.is_symlink():
        log.warning("Refusing to overwrite non-symlink %s", link)
        return False
    if link.is_symlink():
        try:
            if link.resolve() == src.resolve():
                return True
        except OSError:
            pass
        link.unlink(missing_ok=True)
    elif link.exists():
        log.warning("Refusing to overwrite non-symlink %s", link)
        return False
    link.symlink_to(src.resolve(), target_is_directory=False)
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

    Supports standard ``Shaders`` / ``Textures`` at clone root, nested folders that
    directly contain shader or texture files, and a per-file symlink fallback for
    scattered ``.fx`` / ``.fxh`` (and texture extensions) under the clone.
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
    used_file_fallback = False

    shaders_src = _find_subdir_case_insensitive(clone_dir, "Shaders")
    textures_src = _find_subdir_case_insensitive(clone_dir, "Textures")
    if shaders_src is not None and not _tree_has_shader_files(shaders_src):
        shaders_src = None
    if textures_src is not None and not _tree_has_texture_files(textures_src):
        textures_src = None

    if shaders_src is not None or textures_src is not None:
        if shaders_src is not None:
            link = sh_dst_root / rid
            if _symlink_dir_or_skip(link, shaders_src, repo_id=rid):
                new_links.append(str(link.absolute()))
        if textures_src is not None:
            link = tx_dst_root / rid
            if _symlink_dir_or_skip(link, textures_src, repo_id=rid):
                new_links.append(str(link.absolute()))
    else:
        nested_sh = _discover_nested_shader_roots(clone_dir)
        nested_tx = _discover_nested_texture_roots(clone_dir)
        if nested_sh or nested_tx:
            if nested_sh:
                if len(nested_sh) == 1:
                    link = sh_dst_root / rid
                    if _symlink_dir_or_skip(link, nested_sh[0], repo_id=rid):
                        new_links.append(str(link.absolute()))
                else:
                    for root in nested_sh:
                        sub = sh_dst_root / rid / root.name
                        if _symlink_dir_or_skip(sub, root, repo_id=rid):
                            new_links.append(str(sub.absolute()))
            if nested_tx:
                if len(nested_tx) == 1:
                    link = tx_dst_root / rid
                    if _symlink_dir_or_skip(link, nested_tx[0], repo_id=rid):
                        new_links.append(str(link.absolute()))
                else:
                    for root in nested_tx:
                        sub = tx_dst_root / rid / root.name
                        if _symlink_dir_or_skip(sub, root, repo_id=rid):
                            new_links.append(str(sub.absolute()))
        else:
            fx_files = _collect_shader_files_for_fallback(clone_dir)
            tex_files = _collect_texture_files_for_fallback(clone_dir)
            if fx_files:
                used_file_fallback = True
                try:
                    clone_abs = clone_dir.resolve()
                except OSError:
                    clone_abs = clone_dir
                for src in fx_files:
                    try:
                        rel = src.resolve().relative_to(clone_abs)
                    except ValueError:
                        rel = src.relative_to(clone_dir)
                    dst = sh_dst_root / rid / rel
                    if _symlink_file_or_skip(dst, src, repo_id=rid):
                        new_links.append(str(dst.absolute()))
            if tex_files and not nested_tx:
                used_file_fallback = True
                try:
                    clone_abs = clone_dir.resolve()
                except OSError:
                    clone_abs = clone_dir
                for src in tex_files:
                    try:
                        rel = src.resolve().relative_to(clone_abs)
                    except ValueError:
                        rel = src.relative_to(clone_dir)
                    dst = tx_dst_root / rid / rel
                    if _symlink_file_or_skip(dst, src, repo_id=rid):
                        new_links.append(str(dst.absolute()))

    if not new_links:
        log.warning("Repo %r: no shader or texture files found — skipping enable", rid)
        manifest.symlinks_by_repo_id.pop(rid, None)
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
        save_game_manifest(paths, manifest)
        for link in old_links:
            _prune_empty_parents(Path(link), gd)
        return False

    if used_file_fallback:
        log.warning(
            "Repo %r: non-standard layout — file-based symlink fallback in use; prefer Shaders/ and Textures/ roots when possible",
            rid,
        )

    manifest.symlinks_by_repo_id[rid] = new_links
    if rid not in manifest.enabled_repo_ids:
        manifest.enabled_repo_ids.append(rid)
    save_game_manifest(paths, manifest)
    for link in old_links:
        _prune_empty_parents(Path(link), gd)
    return True
