"""Download and cache crosire/d3d8to9 ``d3d8.dll`` for DirectX 8 + ReShade (D3D9) installs."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from pathlib import Path

from reshade_shader_manager.core.exceptions import RSMError
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.targets import pe_machine_is_64bit

log = logging.getLogger(__name__)

# Pinned upstream release (bump intentionally when testing new builds).
D3D8TO9_RELEASE_TAG = "v1.15.1"
D3D8TO9_USER_AGENT = "reshade-shader-manager/d3d8to9-fetch"


def _download_url() -> str:
    return f"https://github.com/crosire/d3d8to9/releases/download/{D3D8TO9_RELEASE_TAG}/d3d8.dll"


def _verify_arch(path: Path, *, want_64: bool) -> None:
    is_64 = pe_machine_is_64bit(path)
    if is_64 is None:
        raise RSMError(f"Downloaded d3d8to9 file is not a valid PE image: {path}")
    if want_64 and not is_64:
        raise RSMError(
            "The official crosire/d3d8to9 release ships a 32-bit d3d8.dll only. "
            "DirectX 8 install with this wrapper is not available for 64-bit games."
        )
    if not want_64 and is_64:
        raise RSMError(
            "Downloaded d3d8.dll is 64-bit but a 32-bit game was selected; refusing to install."
        )


def ensure_d3d8to9_dll(paths: RsmPaths, *, arch: str) -> Path:
    """
    Return path to a cached ``d3d8.dll`` whose PE machine matches ``arch`` (``\"32\"`` or ``\"64\"``).

    Downloads from GitHub releases if missing. Raises :class:`RSMError` on network failure,
    invalid PE, or architecture mismatch.
    """
    if arch not in ("32", "64"):
        raise ValueError(f"invalid arch: {arch!r}")
    want_64 = arch == "64"
    dest = paths.d3d8to9_cached_dll_path(release_tag=D3D8TO9_RELEASE_TAG)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not dest.is_file() or dest.stat().st_size == 0:
        url = _download_url()
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": D3D8TO9_USER_AGENT}, method="GET")
        log.info("Downloading d3d8to9 %s", url)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                tmp.write_bytes(resp.read())
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as e:
            tmp.unlink(missing_ok=True)
            raise RSMError(f"Failed to download d3d8to9 from {url}: {e}") from e
        tmp.replace(dest)

    _verify_arch(dest, want_64=want_64)
    return dest
