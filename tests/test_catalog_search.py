"""Tests for catalog_search substring matching."""

from reshade_shader_manager.ui.catalog_search import (
    catalog_entry_matches,
    normalize_query,
)


def test_normalize_query_strips() -> None:
    assert normalize_query("  foo  ") == "foo"
    assert normalize_query("") == ""
    assert normalize_query("   ") == ""


def test_empty_query_matches_all() -> None:
    assert catalog_entry_matches("", {"name": "x", "author": "", "description": "", "source": "y"})
    assert catalog_entry_matches("   ", {"name": "x"})


def test_case_insensitive_substring() -> None:
    e = {
        "name": "ReShade official shaders",
        "author": "crosire",
        "description": "Default",
        "source": "built-in",
    }
    assert catalog_entry_matches("official", e)
    assert catalog_entry_matches("CRO", e)
    assert catalog_entry_matches("BUILT", e)
    assert not catalog_entry_matches("missing", e)


def test_missing_keys_treated_empty() -> None:
    e: dict[str, str] = {"name": "Only", "source": "upstream"}
    assert catalog_entry_matches("only", e)
    assert catalog_entry_matches("", e)
    assert not catalog_entry_matches("author", e)


def test_custom_fields() -> None:
    e = {"a": "hello", "b": "world"}
    assert catalog_entry_matches("ello", e, fields=("a", "b"))
    assert not catalog_entry_matches("ello", e, fields=("b",))
