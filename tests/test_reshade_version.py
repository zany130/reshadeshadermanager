"""Unit tests for ReShade \"latest\" parsing from GitHub tags payload (no network)."""

from __future__ import annotations

import pytest

from reshade_shader_manager.core.exceptions import VersionResolutionError
from reshade_shader_manager.core.reshade import parse_latest_reshade_version_from_github_tags_payload


def test_picks_highest_semver() -> None:
    data = [
        {"name": "v6.7.0"},
        {"name": "v6.7.3"},
        {"name": "v6.6.99"},
    ]
    assert parse_latest_reshade_version_from_github_tags_payload(data) == "6.7.3"


def test_accepts_uppercase_v_prefix() -> None:
    data = [{"name": "V5.1.2"}]
    assert parse_latest_reshade_version_from_github_tags_payload(data) == "5.1.2"


def test_skips_non_semver_and_non_dict_entries() -> None:
    data = [
        "bad",
        {"name": "nightly"},
        {"name": "v1.0.0"},
        {"oops": 1},
        {"name": "v2.0.0-rc1"},
    ]
    assert parse_latest_reshade_version_from_github_tags_payload(data) == "1.0.0"


def test_not_a_list_raises() -> None:
    with pytest.raises(VersionResolutionError, match="tag list"):
        parse_latest_reshade_version_from_github_tags_payload({})


def test_no_parseable_tags_raises() -> None:
    with pytest.raises(VersionResolutionError, match="Could not parse"):
        parse_latest_reshade_version_from_github_tags_payload([{"name": "foo"}])
