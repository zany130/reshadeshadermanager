"""Graphics API → ReShade proxy name mapping."""

import pytest

from reshade_shader_manager.core.targets import DX8_WRAPPER_BASENAME, GraphicsAPI, proxy_dll_for_api


def test_proxy_dll_dx8_uses_d3d9_for_reshade() -> None:
    assert proxy_dll_for_api(GraphicsAPI.DX8) == "d3d9.dll"


def test_dx8_wrapper_constant() -> None:
    assert DX8_WRAPPER_BASENAME == "d3d8.dll"


@pytest.mark.parametrize(
    ("api", "expected"),
    [
        (GraphicsAPI.OPENGL, "opengl32.dll"),
        (GraphicsAPI.DX9, "d3d9.dll"),
        (GraphicsAPI.DX10, "dxgi.dll"),
        (GraphicsAPI.DX11, "dxgi.dll"),
        (GraphicsAPI.DX12, "dxgi.dll"),
    ],
)
def test_proxy_dll_other_apis(api: GraphicsAPI, expected: str) -> None:
    assert proxy_dll_for_api(api) == expected
