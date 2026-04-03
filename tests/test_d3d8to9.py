"""d3d8to9 cache and PE arch verification."""

import os
from pathlib import Path

import pytest

from reshade_shader_manager.core.d3d8to9 import D3D8TO9_RELEASE_TAG, ensure_d3d8to9_dll
from reshade_shader_manager.core.exceptions import RSMError
from reshade_shader_manager.core.paths import RsmPaths


def test_ensure_d3d8to9_rejects_non_pe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    dest = paths.d3d8to9_cached_dll_path(release_tag=D3D8TO9_RELEASE_TAG)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"not a portable executable")

    with pytest.raises(RSMError, match="not a valid PE"):
        ensure_d3d8to9_dll(paths, arch="32")


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RSM_NETWORK_TEST") != "1", reason="set RSM_NETWORK_TEST=1 for network")
def test_ensure_d3d8to9_official_dll_is_32bit_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Official crosire release is PE32; 64-bit arch must fail without guessing."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    # Populate cache with real upstream DLL (network).
    ensure_d3d8to9_dll(paths, arch="32")
    with pytest.raises(RSMError, match="32-bit d3d8.dll only"):
        ensure_d3d8to9_dll(paths, arch="64")
