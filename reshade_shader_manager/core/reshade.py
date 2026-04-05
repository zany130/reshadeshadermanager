"""ReShade download, extract, install, remove, check."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from reshade_shader_manager.core.exceptions import RSMError, VersionResolutionError
from reshade_shader_manager.core.manifest import GameManifest, save_game_manifest
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.d3d8to9 import ensure_d3d8to9_dll
from reshade_shader_manager.core.targets import DX8_WRAPPER_BASENAME, GraphicsAPI, proxy_dll_for_api

log = logging.getLogger(__name__)

RESHADE_GITHUB_TAGS_API = "https://api.github.com/repos/crosire/reshade/tags?per_page=100"
RESHADE_DOWNLOAD_BASE = "https://reshade.me/downloads"
USER_AGENT = "reshade-shader-manager/0.1"

# HLSL / D3D compile support for ReShade under Wine/Proton; never tracked in manifest (see install/remove).
_D3D_COMPILER_BASENAME = "d3dcompiler_47.dll"


def _http_json_get(url: str, *, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — curated URL
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _read_latest_cache(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("version")
        if isinstance(v, str) and v.strip():
            return v.strip()
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return None


def _write_latest_cache(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"version": version}, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def parse_latest_reshade_version_from_github_tags_payload(data: Any) -> str:
    """
    Parse JSON from GitHub ``GET /repos/crosire/reshade/tags`` (list of tag objects).

    Returns the highest ``x.y.z`` semver string found in ``name`` fields (``v`` prefix allowed).
    """
    if not isinstance(data, list):
        raise VersionResolutionError("GitHub API response missing tag list")

    versions: list[tuple[int, int, int]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        raw = name.strip()
        if raw[:1] in ("v", "V"):
            raw = raw[1:]
        parts = raw.split(".")
        if len(parts) != 3:
            continue
        if not all(p.isdigit() for p in parts):
            continue
        versions.append((int(parts[0]), int(parts[1]), int(parts[2])))

    if not versions:
        raise VersionResolutionError("Could not parse any semver tags from GitHub")

    v = max(versions)
    return f"{v[0]}.{v[1]}.{v[2]}"


def fetch_latest_reshade_version_from_github() -> str:
    """
    Resolve "latest" from GitHub tags for ``crosire/reshade``.

    Note: GitHub's ``/releases/latest`` endpoint is returning 404 in this environment,
    but the tags endpoint works and includes versions like ``v6.7.3``.
    """
    data = _http_json_get(RESHADE_GITHUB_TAGS_API)
    return parse_latest_reshade_version_from_github_tags_payload(data)


def resolve_reshade_version(requested: str, paths: RsmPaths) -> str:
    """
    Resolve ``requested`` version string.

    If ``requested`` is ``latest`` (case-insensitive), use GitHub latest release;
    on failure fall back to ``reshade_latest_cache.json``; if none, raise
    :class:`VersionResolutionError`.
    """
    r = requested.strip()
    if r.lower() != "latest":
        return r
    cache_path = paths.reshade_latest_cache_path()
    try:
        v = fetch_latest_reshade_version_from_github()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        log.warning("Could not fetch latest ReShade from GitHub: %s", e)
        cached = _read_latest_cache(cache_path)
        if cached:
            log.info("Using cached ReShade version %s", cached)
            return cached
        raise VersionResolutionError(
            "Could not resolve 'latest' (network or GitHub error) and no cached version exists. "
            "Specify an explicit ReShade version (e.g. 6.7.3)."
        ) from e
    _write_latest_cache(cache_path, v)
    return v


def download_reshade_installer(version: str, paths: RsmPaths, *, addon: bool) -> Path:
    """Download installer EXE if missing; return path to the file."""
    dest = paths.reshade_download_path(version, addon=addon)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    suffix = "_Addon" if addon else ""
    fname = f"ReShade_Setup_{version}{suffix}.exe"
    url = f"{RESHADE_DOWNLOAD_BASE}/{fname}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    log.info("Downloading %s", url)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            tmp.write_bytes(resp.read())
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as e:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise RSMError(f"Failed to download ReShade installer from {url}: {e}") from e
    tmp.replace(dest)
    return dest


def extract_reshade_installer(exe_path: Path, extract_root: Path) -> None:
    """Extract zip-based ReShade setup EXE into ``extract_root``."""
    if not zipfile.is_zipfile(exe_path):
        raise RSMError(f"Downloaded file is not a zip-based installer: {exe_path}")
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(exe_path, "r") as zf:
        zf.extractall(extract_root)


def _pick_shortest(paths: list[Path]) -> Path:
    return min(paths, key=lambda p: (len(p.parts), str(p)))


def _extract_has_payload(extract_root: Path) -> bool:
    if not extract_root.is_dir():
        return False
    for name in ("ReShade64.dll", "ReShade32.dll"):
        if any(extract_root.rglob(name)):
            return True
    return False


def _ensure_d3dcompiler_47(
    game_dir: Path,
    *,
    d3d_src_from_extract: Path | None,
    extract_root: Path,
    paths: RsmPaths,
) -> None:
    """
    If ``<game_dir>/d3dcompiler_47.dll`` is missing, copy from the ReShade extract or XDG cache.

    Does not overwrite an existing file. Does not add the DLL to ``installed_reshade_files`` so
    uninstall does not remove it (one-way ensure for Proton/Wine compatibility).
    """
    dest = game_dir / _D3D_COMPILER_BASENAME
    if dest.exists():
        return

    src = d3d_src_from_extract if (d3d_src_from_extract and d3d_src_from_extract.is_file()) else None
    if src is None:
        for p in extract_root.rglob(_D3D_COMPILER_BASENAME):
            if p.is_file():
                src = p
                break
    if src is None:
        cache = paths.cached_d3dcompiler_path()
        if cache.is_file():
            src = cache
    if src is None:
        log.warning(
            "Could not locate %s in ReShade installer or cache; Proton/Wine may need it manually.",
            _D3D_COMPILER_BASENAME,
        )
        return

    shutil.copy2(src, dest)
    try:
        cache = paths.cached_d3dcompiler_path()
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, cache)
    except OSError as e:
        log.debug("Could not refresh %s cache: %s", _D3D_COMPILER_BASENAME, e)
    log.info("Installed %s for ReShade compatibility", _D3D_COMPILER_BASENAME)


def find_payload_dlls(extract_root: Path, arch: str) -> tuple[Path, Path | None]:
    """Return ``(ReShade{32|64}.dll path, d3dcompiler_47.dll or None)``."""
    name = "ReShade64.dll" if arch == "64" else "ReShade32.dll"
    matches = [p for p in extract_root.rglob(name) if p.is_file()]
    if not matches:
        raise RSMError(f"{name} not found under {extract_root}")
    reshade_dll = _pick_shortest(matches)
    d3d_matches = [p for p in extract_root.rglob(_D3D_COMPILER_BASENAME) if p.is_file()]
    d3d = _pick_shortest(d3d_matches) if d3d_matches else None
    return reshade_dll, d3d


def install_reshade(
    *,
    paths: RsmPaths,
    manifest: GameManifest,
    graphics_api: str,
    reshade_version: str,
    variant: str,
) -> GameManifest:
    """
    Install ReShade proxy + ensure ``d3dcompiler_47.dll`` is present (Wine/Proton compatibility).

    Only one active ReShade runtime per game directory. Before copying new DLLs, any files still
    listed in ``installed_reshade_files`` are removed from disk (except ``d3dcompiler_47.dll``,
    which is never deleted here) so switching API does not leave orphan proxies. The manifest
    list is then **replaced** with the new install set (no merge across runs).

    **DX8:** installs crosire ``d3d8to9`` as ``d3d8.dll`` and ReShade as ``d3d9.dll`` (32-bit games only
    with current upstream release).

    ``d3dcompiler_47.dll`` is ensured next to the proxy if missing (from the installer or cache);
    it is **not** listed in ``installed_reshade_files`` and is **not** removed by
    :func:`remove_reshade_binaries`.

    Does not create or edit ``ReShade.ini`` (ReShade manages that at runtime). Does not clear
    shader symlinks or ``enabled_repo_ids``.
    """
    api = GraphicsAPI(graphics_api)

    game_dir = Path(manifest.game_dir)
    if not game_dir.is_dir():
        raise RSMError(f"game_dir is not a directory: {game_dir}")

    # Single-runtime reinstall: remove prior tracked binaries only (not INI / symlinks).
    # Never remove d3dcompiler_47.dll here — it may be user-managed or from a prior ensure.
    for name in list(manifest.installed_reshade_files):
        if name == _D3D_COMPILER_BASENAME:
            continue
        prev = game_dir / name
        if prev.is_file():
            prev.unlink()

    resolved = resolve_reshade_version(reshade_version, paths)
    addon = variant == "addon"
    exe = download_reshade_installer(resolved, paths, addon=addon)
    extdir = paths.reshade_extract_dir(resolved)
    if not _extract_has_payload(extdir):
        extract_reshade_installer(exe, extdir)
    reshade_src, d3d_src = find_payload_dlls(extdir, manifest.reshade_arch)
    dest_name = proxy_dll_for_api(api)

    installed: list[str] = []
    if api is GraphicsAPI.DX8:
        wrapper_src = ensure_d3d8to9_dll(paths, arch=manifest.reshade_arch)
        shutil.copy2(wrapper_src, game_dir / DX8_WRAPPER_BASENAME)
        installed.append(DX8_WRAPPER_BASENAME)
    shutil.copy2(reshade_src, game_dir / dest_name)
    installed.append(dest_name)
    _ensure_d3dcompiler_47(game_dir, d3d_src_from_extract=d3d_src, extract_root=extdir, paths=paths)

    manifest.reshade_version = resolved
    manifest.reshade_variant = "addon" if addon else "standard"
    manifest.graphics_api = graphics_api
    manifest.installed_reshade_files = installed

    save_game_manifest(paths, manifest)
    return manifest


def remove_reshade_binaries(*, paths: RsmPaths, manifest: GameManifest) -> list[str]:
    """
    Remove only files listed in ``installed_reshade_files``; do not delete ``ReShade.ini``,
    ``d3dcompiler_47.dll``, shader symlinks, or ``enabled_repo_ids``. Returns warnings for missing files.
    """
    game_dir = Path(manifest.game_dir)
    warnings: list[str] = []
    for name in list(manifest.installed_reshade_files):
        if name == _D3D_COMPILER_BASENAME:
            continue
        p = game_dir / name
        if p.is_file():
            p.unlink()
        else:
            warnings.append(f"missing (skipped): {p}")
    manifest.installed_reshade_files = []
    save_game_manifest(paths, manifest)
    return warnings


@dataclass
class ReShadeCheckResult:
    ok: bool
    missing_files: list[str]
    warnings: list[str]


def check_reshade(manifest: GameManifest) -> ReShadeCheckResult:
    """Verify ``installed_reshade_files`` exist under ``game_dir``."""
    game_dir = Path(manifest.game_dir)
    missing: list[str] = []
    for name in manifest.installed_reshade_files:
        p = game_dir / name
        if not p.is_file():
            missing.append(str(p))
    return ReShadeCheckResult(ok=len(missing) == 0, missing_files=missing, warnings=[])
