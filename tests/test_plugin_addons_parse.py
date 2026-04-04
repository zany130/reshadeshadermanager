"""Plugin add-on Addons.ini parsing and stable ids."""

from reshade_shader_manager.core.plugin_addons_parse import (
    parse_and_normalize_addons_ini,
    parse_addons_ini_sections,
    stable_plugin_addon_id,
)


SAMPLE_INI = """
# [00]
# PackageName=Commented out
[01]
PackageName=FreePIE by crosire
PackageDescription=Adds support for reading FreePIE input data.
DownloadUrl32=https://example.com/freepie.addon32
DownloadUrl64=https://example.com/freepie.addon64
RepositoryUrl=https://github.com/crosire/reshade/tree/main/examples/02-freepie

[02]
PackageName=Frame Capture by murchalloo
PackageDescription=Export depth
DownloadUrl64=https://github.com/murchalloo/reshade-addons/releases/download/1.0.2/frame_capture.addon
RepositoryUrl=https://github.com/murchalloo/reshade-addons
"""


def test_parse_skips_comment_only_blocks() -> None:
    sections = parse_addons_ini_sections(SAMPLE_INI)
    secs = [s for s, _ in sections]
    assert "00" not in secs
    assert "01" in secs
    assert "02" in secs


def test_stable_id_ignores_section_when_metadata_same() -> None:
    a = stable_plugin_addon_id(
        package_name="Same Name",
        repository_url="https://github.com/a/a",
        download_url_32="",
        download_url_64="https://x/x",
        download_url="",
    )
    b = stable_plugin_addon_id(
        package_name="Same Name",
        repository_url="https://github.com/a/a",
        download_url_32="",
        download_url_64="https://x/x",
        download_url="",
    )
    assert a == b


def test_different_download_changes_id() -> None:
    a = stable_plugin_addon_id(
        package_name="Same Name",
        repository_url="https://github.com/a/a",
        download_url_32="",
        download_url_64="https://x/one",
        download_url="",
    )
    b = stable_plugin_addon_id(
        package_name="Same Name",
        repository_url="https://github.com/a/a",
        download_url_32="",
        download_url_64="https://x/two",
        download_url="",
    )
    assert a != b


def test_normalize_includes_upstream_section() -> None:
    rows = parse_and_normalize_addons_ini(SAMPLE_INI)
    by_sec = {r["upstream_section"]: r for r in rows}
    assert by_sec["01"]["name"].startswith("FreePIE")
    assert by_sec["01"]["download_url_32"].endswith("addon32")
    assert by_sec["02"]["download_url_32"] == ""
    assert by_sec["02"]["download_url_64"].endswith("frame_capture.addon")


def test_skips_section_without_package_name() -> None:
    ini = """
[bad]
RepositoryUrl=https://github.com/x/x
"""
    assert parse_and_normalize_addons_ini(ini) == []
