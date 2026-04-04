"""Install and remove ReShade *plugin* add-on DLLs (copies in game root; metadata in manifest)."""

from __future__ import annotations

import logging
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from reshade_shader_manager.core.exceptions import RSMError
from reshade_shader_manager.core.manifest import GameManifest, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.targets import pe_machine_is_64bit

log = logging.getLogger(__name__)

USER_AGENT = "reshade-shader-manager/0.2 (plugin add-on install)"


def resolve_download_url_for_arch(entry: dict[str, str], *, arch: str) -> str:
    """
    Return URL for the selected game architecture.

    Uses arch-specific URLs when present; otherwise ``download_url`` only if set
    (payload must pass a PE machine check after download).
    """
    if arch not in ("32", "64"):
        raise ValueError(f"invalid arch: {arch!r}")
    u32 = entry.get("download_url_32", "").strip()
    u64 = entry.get("download_url_64", "").strip()
    u1 = entry.get("download_url", "").strip()
    repo = entry.get("repository_url", "").strip()
    name = entry.get("name", entry.get("id", "?"))

    if not u32 and not u64 and not u1:
        if repo:
            raise RSMError(
                f"Plugin add-on {name!r} has no download links in the upstream catalog "
                f"(repository-only entry). Install from the vendor or add URLs in plugin_addons.json."
            )
        raise RSMError(
            f"Plugin add-on {name!r} has no download links in the upstream catalog."
        )

    if arch == "64":
        if u64:
            return u64
        if u1:
            return u1
        raise RSMError(
            f"Plugin add-on {name!r} has no 64-bit download URL "
            f"(this add-on may be 32-bit only or list a single-architecture link)."
        )
    if u32:
        return u32
    if u1:
        return u1
    raise RSMError(
        f"Plugin add-on {name!r} has no 32-bit download URL "
        f"(this add-on may be 64-bit only or list a single-architecture link)."
    )


def installability_detail(entry: dict[str, str], *, arch: str) -> tuple[bool, str]:
    """
    Return ``(True, \"\")`` if :func:`resolve_download_url_for_arch` succeeds, else ``(False, reason)``.
    Used by the UI to disable rows that cannot be installed for the current game architecture.
    """
    try:
        resolve_download_url_for_arch(entry, arch=arch)
        return True, ""
    except RSMError as e:
        return False, str(e)


def _http_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            tmp.write_bytes(resp.read())
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as e:
        tmp.unlink(missing_ok=True)
        raise RSMError(f"Failed to download plugin add-on from {url}: {e}") from e
    tmp.replace(dest)


def _artifact_paths(cache_dir: Path, url: str) -> tuple[Path, Path]:
    name = Path(urllib.parse.urlparse(url).path).name or "download.bin"
    if not name or name in (".", ".."):
        name = "download.bin"
    archive = cache_dir / name
    extract_root = cache_dir / "_extract"
    return archive, extract_root


def download_artifact(paths: RsmPaths, addon_id: str, url: str) -> tuple[Path, Path]:
    """Return ``(archive_path, extract_root)``; download if missing."""
    cache_dir = paths.plugin_addon_artifact_dir(addon_id, url)
    archive, extract_root = _artifact_paths(cache_dir, url)
    if not archive.is_file() or archive.stat().st_size == 0:
        _http_download(url, archive)
    return archive, extract_root


def _collect_zip_candidate_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        low = path.name.lower()
        if low.endswith((".addon32", ".addon64", ".addon", ".dll")):
            out.append(path)
    return out


def pick_payload_from_zip_extract(extract_root: Path, *, arch: str) -> Path:
    """
    Fail closed: return exactly one payload file for ``arch``, or raise :class:`RSMError`.
    """
    want_64 = arch == "64"
    paths = _collect_zip_candidate_files(extract_root)
    a64 = [p for p in paths if p.name.lower().endswith(".addon64")]
    a32 = [p for p in paths if p.name.lower().endswith(".addon32")]
    a_plain = [
        p
        for p in paths
        if p.name.lower().endswith(".addon")
        and not p.name.lower().endswith((".addon32", ".addon64"))
    ]
    dlls = [p for p in paths if p.suffix.lower() == ".dll"]

    def pe_matches(p: Path) -> bool:
        is64 = pe_machine_is_64bit(p)
        if is64 is None:
            return False
        return is64 == want_64

    label = "64-bit" if want_64 else "32-bit"

    if want_64:
        if len(a64) == 1:
            return a64[0]
        if len(a64) > 1:
            raise RSMError("ZIP contains multiple .addon64 files; refusing to guess which to install.")
        if len(a32) >= 1 and not a_plain and not [p for p in dlls if pe_matches(p)]:
            raise RSMError("ZIP appears to contain only 32-bit add-on payloads; cannot install for 64-bit.")
    else:
        if len(a32) == 1:
            return a32[0]
        if len(a32) > 1:
            raise RSMError("ZIP contains multiple .addon32 files; refusing to guess which to install.")
        if len(a64) >= 1 and not a_plain and not [p for p in dlls if pe_matches(p)]:
            raise RSMError("ZIP appears to contain only 64-bit add-on payloads; cannot install for 32-bit.")

    plain_ok = [p for p in a_plain if pe_matches(p)]
    if len(plain_ok) == 1:
        return plain_ok[0]
    if len(a_plain) >= 1 and len(plain_ok) != 1:
        raise RSMError(
            f"ZIP contains ambiguous .addon file(s) for {label} (PE check inconclusive or multiple matches)."
        )

    dll_ok = [p for p in dlls if pe_matches(p)]
    if len(dll_ok) == 1:
        return dll_ok[0]
    if len(dll_ok) > 1:
        raise RSMError(f"ZIP contains multiple {label} DLL candidates; refusing to guess.")
    raise RSMError(f"Could not identify a single {label} add-on payload in the ZIP.")


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if not zipfile.is_zipfile(zip_path):
        raise RSMError(f"Not a zip file: {zip_path}")
    root_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/") or not name.strip():
                continue
            target = (dest / name).resolve()
            if root_resolved not in target.parents and target != root_resolved:
                raise RSMError("ZIP entry escapes extract directory; refusing to extract.")
        zf.extractall(dest)


def prepare_payload_file(
    paths: RsmPaths,
    addon_id: str,
    url: str,
    *,
    arch: str,
) -> Path:
    """Download if needed; return path to a single DLL/addon file to copy into the game root."""
    archive, extract_root = download_artifact(paths, addon_id, url)
    if zipfile.is_zipfile(archive):
        if extract_root.is_dir():
            shutil.rmtree(extract_root, ignore_errors=True)
        _safe_extract_zip(archive, extract_root)
        return pick_payload_from_zip_extract(extract_root, arch=arch)
    is64 = pe_machine_is_64bit(archive)
    if is64 is None:
        raise RSMError(f"Downloaded file is not a valid PE image: {archive.name}")
    if is64 != (arch == "64"):
        raise RSMError(
            f"Downloaded add-on is {'64' if is64 else '32'}-bit PE but the game target is {arch}-bit."
        )
    return archive


def _tracked_root_basenames(manifest: GameManifest, *, exclude_addon_id: str | None = None) -> set[str]:
    s: set[str] = set()
    for aid, basenames in manifest.plugin_addon_root_copies.items():
        if exclude_addon_id is not None and aid == exclude_addon_id:
            continue
        for b in basenames:
            s.add(b)
    return s


def _assert_install_conflict(
    game_dir: Path,
    basename: str,
    manifest: GameManifest,
    *,
    installing_addon_id: str,
) -> None:
    if "/" in basename or "\\" in basename or basename in (".", ".."):
        raise RSMError(f"Unsafe add-on target basename: {basename!r}")
    if basename in manifest.installed_reshade_files:
        raise RSMError(
            f"File name {basename!r} is already used by a managed ReShade install; "
            "remove or change ReShade API before installing this add-on."
        )
    for other_id, roots in manifest.plugin_addon_root_copies.items():
        if other_id == installing_addon_id:
            continue
        if basename in roots:
            raise RSMError(
                f"File name {basename!r} is already used by plugin add-on {other_id!r}. "
                "Disable that add-on first."
            )
    dest = game_dir / basename
    if dest.exists() or dest.is_symlink():
        prev = manifest.plugin_addon_root_copies.get(installing_addon_id, [])
        if basename in prev:
            return
        raise RSMError(
            f"{dest} already exists and is not managed by RSM for this add-on; "
            "remove or rename it manually (RSM does not overwrite unmanaged files)."
        )


def _remove_addon_install(paths: RsmPaths, manifest: GameManifest, game_dir: Path, addon_id: str) -> None:
    """Remove root copies and companion symlinks for one add-on; update manifest dicts in memory."""
    gd = game_dir.resolve()
    for rel in list(manifest.plugin_addon_root_copies.get(addon_id, [])):
        if "/" in rel or "\\" in rel:
            log.warning("Skipping non-basename managed path %s", rel)
            continue
        p = gd / rel
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
        except OSError as e:
            log.warning("Could not remove %s: %s", p, e)
    for abs_s in list(manifest.plugin_addon_companion_symlinks.get(addon_id, [])):
        p = Path(abs_s)
        try:
            if p.is_symlink():
                p.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Could not remove companion symlink %s: %s", p, e)
    manifest.plugin_addon_root_copies.pop(addon_id, None)
    manifest.plugin_addon_companion_symlinks.pop(addon_id, None)


def apply_plugin_addon_installation(
    *,
    paths: RsmPaths,
    manifest: GameManifest,
    game_dir: Path,
    desired_plugin_addon_ids: set[str],
    catalog_by_id: dict[str, dict[str, str]],
) -> None:
    """
    Reconcile on-disk plugin add-ons and manifest to match ``desired_plugin_addon_ids``.

    Copies payloads into ``game_dir`` (never symlinks for root DLLs). Fails on conflicts
    with unmanaged files or ReShade-tracked DLLs. ZIP archives use fail-closed payload choice.
    """
    gd = game_dir.resolve()
    if not gd.is_dir():
        raise RSMError(f"game_dir is not a directory: {gd}")

    arch = manifest.reshade_arch
    if arch not in ("32", "64"):
        raise RSMError(f"Manifest has invalid reshade_arch: {arch!r}")

    unknown = desired_plugin_addon_ids - set(catalog_by_id.keys())
    if unknown:
        log.warning("Skipping unknown plugin add-on ids: %s", sorted(unknown))
    effective_desired = {x for x in desired_plugin_addon_ids if x in catalog_by_id}

    # Remove deselected add-ons first
    for aid in list(manifest.plugin_addon_root_copies.keys()):
        if aid not in desired_plugin_addon_ids:
            _remove_addon_install(paths, manifest, gd, aid)

    for aid in sorted(effective_desired):
        entry = catalog_by_id.get(aid)
        if not entry:
            log.warning("Unknown plugin add-on id %r — skipped", aid)
            continue
        try:
            url = resolve_download_url_for_arch(entry, arch=arch)
        except RSMError as e:
            log.debug("Plugin add-on %r: %s", aid, e)
            raise

        _remove_addon_install(paths, manifest, gd, aid)

        payload = prepare_payload_file(paths, aid, url, arch=arch)
        dest_basename = payload.name
        _assert_install_conflict(gd, dest_basename, manifest, installing_addon_id=aid)

        dest = gd / dest_basename
        shutil.copy2(payload, dest)
        manifest.plugin_addon_root_copies[aid] = [dest_basename]
        manifest.plugin_addon_companion_symlinks.setdefault(aid, [])

    manifest.enabled_plugin_addon_ids = sorted(manifest.plugin_addon_root_copies.keys())
    save_game_manifest(paths, manifest)
