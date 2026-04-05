"""Per-game shader projection: symlinks from global clones into the game tree.

Shader repos are merged into shared ``reshade-shaders/Shaders`` and
``reshade-shaders/Textures`` trees while preserving each repository's internal
relative paths. If two repositories would install the same destination path,
the earlier repo (deterministic sort order) wins and the whole later repo is
skipped — we do not relocate individual files, because moving only some files
would desynchronize include resolution from what shader sources expect.

Correctness requires a consistent tree: ``#include "includes/x.fxh"`` resolves
relative to the effect's location and the configured search roots; splitting
conflicts by renaming or moving single files can leave includes pointing at the
wrong repo's copy while other files still reference the original layout.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from reshade_shader_manager.core.git_sync import clone_or_pull
from reshade_shader_manager.core.manifest import GameManifest, load_game_manifest, new_game_manifest, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths, canonical_game_dir

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
        game_abs = canonical_game_dir(game_dir)
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
            if next_cur == cur:
                break
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


def _walk_files_under(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            files.append(Path(dirpath) / fn)
    files.sort(key=lambda p: str(p).lower())
    return files


def _rel_from_clone(src: Path, clone_abs: Path) -> Path:
    try:
        return src.resolve().relative_to(clone_abs)
    except ValueError:
        return src.relative_to(clone_abs)


def _enumerate_merged_projection_entries(clone_dir: Path) -> tuple[list[tuple[str, Path]], bool]:
    """
    Map clone contents to canonical destination keys ``Shaders/<rel>`` or ``Textures/<rel>``
    (forward slashes). Second return value is True when the scattered-file fallback was used.
    """
    entries: list[tuple[str, Path]] = []
    used_fallback = False

    shaders_src = _find_subdir_case_insensitive(clone_dir, "Shaders")
    textures_src = _find_subdir_case_insensitive(clone_dir, "Textures")
    if shaders_src is not None and not _tree_has_shader_files(shaders_src):
        shaders_src = None
    if textures_src is not None and not _tree_has_texture_files(textures_src):
        textures_src = None

    if shaders_src is not None or textures_src is not None:
        if shaders_src is not None:
            for f in _walk_files_under(shaders_src):
                rel = f.relative_to(shaders_src)
                entries.append((f"Shaders/{rel.as_posix()}", f))
        if textures_src is not None:
            for f in _walk_files_under(textures_src):
                rel = f.relative_to(textures_src)
                entries.append((f"Textures/{rel.as_posix()}", f))
        entries.sort(key=lambda t: t[0])
        return entries, False

    nested_sh = _discover_nested_shader_roots(clone_dir)
    nested_tx = _discover_nested_texture_roots(clone_dir)
    if nested_sh or nested_tx:
        if nested_sh:
            if len(nested_sh) == 1:
                root = nested_sh[0]
                for f in _walk_files_under(root):
                    rel = f.relative_to(root)
                    entries.append((f"Shaders/{rel.as_posix()}", f))
            else:
                for root in nested_sh:
                    for f in _walk_files_under(root):
                        rel = f.relative_to(root)
                        entries.append((f"Shaders/{root.name}/{rel.as_posix()}", f))
        if nested_tx:
            if len(nested_tx) == 1:
                root = nested_tx[0]
                for f in _walk_files_under(root):
                    rel = f.relative_to(root)
                    entries.append((f"Textures/{rel.as_posix()}", f))
            else:
                for root in nested_tx:
                    for f in _walk_files_under(root):
                        rel = f.relative_to(root)
                        entries.append((f"Textures/{root.name}/{rel.as_posix()}", f))
        entries.sort(key=lambda t: t[0])
        return entries, False

    try:
        clone_abs = clone_dir.resolve()
    except OSError:
        clone_abs = clone_dir
    fx_files = _collect_shader_files_for_fallback(clone_dir)
    tex_files = _collect_texture_files_for_fallback(clone_dir)
    if fx_files:
        used_fallback = True
        for src in fx_files:
            rel = _rel_from_clone(src, clone_abs)
            entries.append((f"Shaders/{rel.as_posix()}", src))
    if tex_files and not nested_tx:
        used_fallback = True
        for src in tex_files:
            rel = _rel_from_clone(src, clone_abs)
            entries.append((f"Textures/{rel.as_posix()}", src))
    entries.sort(key=lambda t: t[0])
    return entries, used_fallback


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


def _link_path_for_dest_key(rs_base: Path, dest_key: str) -> Path:
    parts = dest_key.split("/")
    return rs_base.joinpath(*parts)


def _recorded_path_to_dest_key(game_dir: Path, link_path_str: str) -> str | None:
    try:
        p = Path(link_path_str).absolute()
    except OSError:
        return None
    try:
        gd = canonical_game_dir(game_dir)
    except OSError:
        gd = Path(game_dir)
    rs = gd / "reshade-shaders"
    sh = rs / "Shaders"
    tx = rs / "Textures"
    try:
        r = p.relative_to(sh)
        return f"Shaders/{r.as_posix()}"
    except ValueError:
        pass
    try:
        r = p.relative_to(tx)
        return f"Textures/{r.as_posix()}"
    except ValueError:
        return None


def _occupied_dest_keys_from_manifest(
    manifest: GameManifest,
    game_dir: Path,
    *,
    exclude_repo_id: str | None,
) -> dict[str, str]:
    """Map canonical dest_key -> owning repo id for conflict checks."""
    out: dict[str, str] = {}
    ex = exclude_repo_id.strip().lower() if exclude_repo_id else None
    for rid, links in manifest.symlinks_by_repo_id.items():
        r = rid.strip().lower()
        if ex is not None and r == ex:
            continue
        for link_str in links:
            dk = _recorded_path_to_dest_key(game_dir, link_str)
            if dk is None:
                log.warning(
                    "Recorded path %r is not under Shaders/ or Textures/; ignoring for conflict check",
                    link_str,
                )
                continue
            out[dk] = r
    return out


def _display_dest_key_for_log(dest_key: str) -> str:
    if dest_key.startswith("Shaders/"):
        return dest_key[len("Shaders/") :]
    if dest_key.startswith("Textures/"):
        return dest_key[len("Textures/") :]
    return dest_key


def _log_repo_skip_conflict(dest_key: str, winner_repo: str, skipped_repo: str) -> None:
    display = _display_dest_key_for_log(dest_key)
    log.warning(
        "Shader path conflict: %r is already provided by repo %r. Skipping repo %r.",
        display,
        winner_repo,
        skipped_repo,
    )


def _install_merged_entries(
    *,
    game_dir: Path,
    entries: list[tuple[str, Path]],
    repo_id: str,
) -> list[str]:
    """Create per-file symlinks for merged projection; all-or-nothing for this repo."""
    gd = canonical_game_dir(game_dir)
    rs_base = gd / "reshade-shaders"
    (rs_base / "Shaders").mkdir(parents=True, exist_ok=True)
    (rs_base / "Textures").mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    new_links: list[str] = []
    for dest_key, src in entries:
        link = _link_path_for_dest_key(rs_base, dest_key)
        if not _symlink_file_or_skip(link, src, repo_id=repo_id):
            for c in created:
                try:
                    c.unlink(missing_ok=True)
                except OSError:
                    pass
            return []
        created.append(link)
        new_links.append(str(link.absolute()))
    return new_links


def disable_shader_repo(*, paths: RsmPaths, manifest: GameManifest, repo_id: str) -> None:
    """Remove symlinks recorded for ``repo_id`` and drop it from ``enabled_repo_ids``."""
    rid = repo_id.strip().lower()
    game_dir = canonical_game_dir(manifest.game_dir)
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

    Repos are merged into shared ``Shaders/`` and ``Textures/`` trees. If a repo
    would overlap an earlier repo's destination paths (sorted id order), that
    whole repo is skipped.

    Removes **only** symlink paths currently recorded in the manifest (under
    ``reshade-shaders``), prunes empty directories, then recreates projection.
    Does not run ``git pull`` when ``git_pull`` is False (existing clones are
    reused; missing clones are still cloned).
    """
    m = load_game_manifest(paths, game_dir) or new_game_manifest(game_dir)
    gd = canonical_game_dir(m.game_dir)

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

    owner: dict[str, str] = {}

    for rid in sorted(desired_repo_ids):
        if rid not in catalog_by_id:
            log.warning("Unknown repo id %r — skipped", rid)
            continue
        url = catalog_by_id[rid]["git_url"]
        clone_dir = paths.repo_clone_dir(rid)
        clone_or_pull(clone_dir, url, pull=git_pull)
        entries, used_fb = _enumerate_merged_projection_entries(clone_dir)
        if not entries:
            log.warning("Repo %r: no shader or texture files found — skipping enable", rid)
            continue
        keys = [e[0] for e in entries]
        first_conflict: str | None = None
        for k in keys:
            if k in owner:
                first_conflict = k
                break
        if first_conflict is not None:
            _log_repo_skip_conflict(first_conflict, owner[first_conflict], rid)
            continue
        if used_fb:
            log.warning(
                "Repo %r: non-standard layout — file-based symlink fallback in use; prefer Shaders/ and Textures/ roots when possible",
                rid,
            )
        links = _install_merged_entries(game_dir=gd, entries=entries, repo_id=rid)
        if not links:
            log.warning("Repo %r: failed to create projection symlinks — skipping enable", rid)
            continue
        for k in keys:
            owner[k] = rid
        m.symlinks_by_repo_id[rid] = links
        if rid not in m.enabled_repo_ids:
            m.enabled_repo_ids.append(rid)

    m.enabled_repo_ids = [r for r in sorted(desired_repo_ids) if r in m.symlinks_by_repo_id]
    save_game_manifest(paths, m)


def enable_shader_repo(
    *,
    paths: RsmPaths,
    manifest: GameManifest,
    repo_id: str,
    git_url: str,
    git_pull: bool = True,
) -> bool:
    """
    Clone or update global repo, then project into ``reshade-shaders`` (merged tree).

    Supports standard ``Shaders`` / ``Textures`` at clone root, nested folders that
    directly contain shader or texture files, and a per-file symlink fallback for
    scattered ``.fx`` / ``.fxh`` (and texture extensions) under the clone.
    """
    rid = repo_id.strip().lower()
    clone_dir = paths.repo_clone_dir(rid)
    clone_or_pull(clone_dir, git_url, pull=git_pull)

    gd = canonical_game_dir(manifest.game_dir)

    entries, used_fallback = _enumerate_merged_projection_entries(clone_dir)
    if not entries:
        log.warning("Repo %r: no shader or texture files found — skipping enable", rid)
        return False

    occupied = _occupied_dest_keys_from_manifest(manifest, gd, exclude_repo_id=rid)
    first_conflict: str | None = None
    for dest_key, _src in entries:
        if dest_key in occupied:
            first_conflict = dest_key
            break
    if first_conflict is not None:
        _log_repo_skip_conflict(first_conflict, occupied[first_conflict], rid)
        return False

    old_links = list(manifest.symlinks_by_repo_id.pop(rid, []))
    for s in old_links:
        unlink_recorded_projection_path(gd, Path(s))
    for s in old_links:
        _prune_empty_parents(Path(s), gd)

    new_links = _install_merged_entries(game_dir=gd, entries=entries, repo_id=rid)
    if not new_links:
        log.warning("Repo %r: failed to create projection symlinks — skipping enable", rid)
        manifest.symlinks_by_repo_id.pop(rid, None)
        manifest.enabled_repo_ids = [x for x in manifest.enabled_repo_ids if x != rid]
        save_game_manifest(paths, manifest)
        for link in old_links:
            _prune_empty_parents(Path(link), gd)
        return False

    if used_fallback:
        log.warning(
            "Repo %r: non-standard layout — file-based symlink fallback in use; prefer Shaders/ and Textures/ roots when possible",
            rid,
        )

    manifest.symlinks_by_repo_id[rid] = new_links
    if rid not in manifest.enabled_repo_ids:
        manifest.enabled_repo_ids.append(rid)
    manifest.enabled_repo_ids.sort()
    save_game_manifest(paths, manifest)
    for link in old_links:
        _prune_empty_parents(Path(link), gd)
    return True
