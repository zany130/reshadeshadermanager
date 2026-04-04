"""User ``plugin_addons.json`` and merged plugin add-on catalog (upstream + user)."""

from __future__ import annotations

import json

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_parse import assert_plugin_addon_row


def load_user_plugin_addons(paths: RsmPaths) -> list[dict[str, str]]:
    path = paths.plugin_addons_json()
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("plugin_addons.json must be a JSON object")
    raw = data.get("addons", [])
    if not isinstance(raw, list):
        raise ValueError("plugin_addons.addons must be an array")
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each plugin add-on entry must be an object")
        row = dict(item)
        row["source"] = "user"
        if not row.get("upstream_section"):
            row["upstream_section"] = ""
        out.append(assert_plugin_addon_row(row))
    return out


def upsert_user_plugin_addon(paths: RsmPaths, row: dict[str, str]) -> None:
    """
    Replace or append a user ``plugin_addons.json`` row keyed by ``id``.

    Requires at least one of ``download_url_32``, ``download_url_64``, or ``download_url``.
    """
    if row.get("source") != "user":
        raise ValueError("upsert_user_plugin_addon only accepts source=user rows")
    clean = assert_plugin_addon_row(row)
    if not (
        clean.get("download_url_32", "").strip()
        or clean.get("download_url_64", "").strip()
        or clean.get("download_url", "").strip()
    ):
        raise ValueError("Provide at least one download URL (32-bit, 64-bit, or single URL).")
    user = load_user_plugin_addons(paths)
    rid = clean["id"]
    for i, e in enumerate(user):
        if e["id"] == rid:
            user[i] = clean
            save_user_plugin_addons(paths, user)
            return
    user.append(clean)
    save_user_plugin_addons(paths, user)


def save_user_plugin_addons(paths: RsmPaths, addons: list[dict[str, str]]) -> None:
    for a in addons:
        if a.get("source") != "user":
            raise ValueError("save_user_plugin_addons only persists source=user entries")
        assert_plugin_addon_row(a)
    path = paths.plugin_addons_json()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"addons": addons}, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def merged_plugin_addon_catalog(
    paths: RsmPaths,
    upstream: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """
    Merge upstream (``Addons.ini``) then user ``plugin_addons.json``.

    On duplicate ``id``, **user** entry wins (same rule as shader ``merged_catalog``).
    """
    by_id: dict[str, dict[str, str]] = {}
    order: list[str] = []

    def add_list(items: list[dict[str, str]]) -> None:
        for row in items:
            rid = row["id"]
            if rid not in by_id:
                order.append(rid)
            by_id[rid] = row

    if upstream:
        add_list(list(upstream))
    add_list(load_user_plugin_addons(paths))
    return [by_id[i] for i in order]
