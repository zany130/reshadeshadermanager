"""ReShade.ini patching."""

from reshade_shader_manager.core.ini import patch_reshade_search_paths


def test_patch_minimal() -> None:
    out = patch_reshade_search_paths(None)
    assert "[GENERAL]" in out
    assert r"EffectSearchPaths=.\reshade-shaders\Shaders**" in out
    assert r"TextureSearchPaths=.\reshade-shaders\Textures**" in out


def test_patch_replace_in_general() -> None:
    src = "[GENERAL]\nEffectSearchPaths=old\nTextureSearchPaths=old2\n[OTHER]\nx=1\n"
    out = patch_reshade_search_paths(
        src,
        effect_search_paths="NEW1",
        texture_search_paths="NEW2",
    )
    assert "NEW1" in out
    assert "NEW2" in out
    assert "old" not in out
    assert "[OTHER]" in out
    assert "x=1" in out


def test_patch_prepends_general_if_missing() -> None:
    src = "[FOO]\na=b\n"
    out = patch_reshade_search_paths(src)
    assert out.startswith("[GENERAL]")
