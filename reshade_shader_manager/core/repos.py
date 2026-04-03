"""Shader repo catalog: built-in (code), user ``repos.json``, merged with PCGW at runtime."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from reshade_shader_manager.core.paths import RsmPaths

_REPO_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

BUILTIN_REPOS: list[dict[str, str]] = [
    {
        "id": "quint",
        "name": "qUINT",
        "git_url": "https://github.com/martymcmodding/qUINT.git",
        "author": "Marty McFly",
        "description": "qUINT shader collection",
        "source": "built-in",
    },
    {
        "id": "reshade-shaders",
        "name": "ReShade official shaders",
        "git_url": "https://github.com/crosire/reshade-shaders.git",
        "author": "crosire",
        "description": "Default ReShade shader repository",
        "source": "built-in",
    },
]


def validate_repo_id(repo_id: str) -> None:
    if not _REPO_ID_PATTERN.match(repo_id):
        raise ValueError(
            "repo id must be 1–64 chars: start with alphanumeric, then [a-z0-9_-]"
        )


def _normalize_repo(entry: Mapping[str, Any], *, source: str) -> dict[str, str]:
    rid = str(entry["id"]).strip().lower()
    validate_repo_id(rid)
    return {
        "id": rid,
        "name": str(entry.get("name", rid)),
        "git_url": str(entry["git_url"]).strip(),
        "author": str(entry.get("author", "")),
        "description": str(entry.get("description", "")),
        "source": source,
    }


def load_user_repos(paths: RsmPaths) -> list[dict[str, str]]:
    path = paths.repos_json()
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("repos.json must be a JSON object")
    raw = data.get("repos", [])
    if not isinstance(raw, list):
        raise ValueError("repos.repos must be an array")
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each repo entry must be an object")
        out.append(_normalize_repo(item, source="user"))
    return out


def save_user_repos(paths: RsmPaths, repos: list[dict[str, str]]) -> None:
    for r in repos:
        if r.get("source") != "user":
            raise ValueError("save_user_repos only persists source=user entries")
    path = paths.repos_json()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"repos": repos}, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def add_user_repo(
    paths: RsmPaths,
    *,
    repo_id: str,
    name: str,
    git_url: str,
    author: str = "",
    description: str = "",
) -> list[dict[str, str]]:
    """Append a user repo; raises if ``id`` already exists in user or built-in."""
    rid = repo_id.strip().lower()
    validate_repo_id(rid)
    user = load_user_repos(paths)
    existing_ids = {r["id"] for r in BUILTIN_REPOS} | {r["id"] for r in user}
    if rid in existing_ids:
        raise ValueError(f"repo id already exists: {rid}")
    entry = _normalize_repo(
        {
            "id": rid,
            "name": name,
            "git_url": git_url,
            "author": author,
            "description": description,
        },
        source="user",
    )
    user.append(entry)
    save_user_repos(paths, user)
    return user


def merged_catalog(
    paths: RsmPaths,
    pcgw_repos: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """
    Merge catalogs: built-in, then PCGW, then user ``repos.json``.

    Later sources override earlier on matching ``id`` (user wins).
    """
    by_id: dict[str, dict[str, str]] = {}
    order: list[str] = []

    def add_list(items: list[dict[str, str]]) -> None:
        for r in items:
            rid = r["id"]
            if rid not in by_id:
                order.append(rid)
            by_id[rid] = r

    add_list(list(BUILTIN_REPOS))
    if pcgw_repos:
        add_list(pcgw_repos)
    add_list(load_user_repos(paths))
    return [by_id[i] for i in order]
