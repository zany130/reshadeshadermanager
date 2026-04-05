"""Simple substring search over catalog dict fields (shared by catalog dialogs)."""

from __future__ import annotations

from collections.abc import Mapping

# Fields used by Manage Shaders / Manage Plugin Add-ons filtering.
DEFAULT_SEARCH_FIELDS: tuple[str, ...] = ("name", "author", "description", "source")


def normalize_query(query: str) -> str:
    """Strip leading/trailing whitespace; empty means no filter."""
    return query.strip()


def catalog_entry_matches(
    query: str,
    entry: Mapping[str, str],
    *,
    fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS,
) -> bool:
    """
    Return True if ``query`` is empty after strip, or if the normalized query
    is a case-insensitive substring of any of the given ``fields`` (missing keys
    treated as empty).
    """
    nq = normalize_query(query)
    if not nq:
        return True
    qf = nq.casefold()
    for key in fields:
        hay = entry.get(key, "")
        if qf in hay.casefold():
            return True
    return False
