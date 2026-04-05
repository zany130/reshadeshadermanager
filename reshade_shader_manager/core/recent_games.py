"""Enumerate recent game manifests by file mtime for the main-window Recents list."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reshade_shader_manager.core.paths import RsmPaths, canonical_game_dir, canonical_game_dir_str

log = logging.getLogger(__name__)

RECENT_GAMES_LIMIT = 6
_PATH_SHORT_MAX = 72


@dataclass(frozen=True)
class RecentGameEntry:
    """One row for the Recent games UI."""

    game_dir: Path
    display_name: str
    path_short: str


def _shorten_path_display(path_str: str, *, max_len: int = _PATH_SHORT_MAX) -> str:
    if len(path_str) <= max_len:
        return path_str
    head = max_len // 2 - 2
    tail = max_len - head - 3
    return path_str[:head] + "…" + path_str[-tail:]


def _display_name_from_manifest(data: dict[str, Any]) -> str:
    exe = data.get("game_exe")
    if exe is not None and str(exe).strip():
        stem = Path(str(exe)).stem
        if stem:
            return stem
    gd = data.get("game_dir")
    if gd is not None and str(gd).strip():
        return Path(str(gd)).name
    return "game"


def _canonical_game_dir_key(game_dir_str: str) -> str | None:
    try:
        return canonical_game_dir_str(game_dir_str)
    except OSError:
        return None


def list_recent_games(paths: RsmPaths, *, limit: int = RECENT_GAMES_LIMIT) -> list[RecentGameEntry]:
    """
    Return up to ``limit`` recent games: manifest files sorted by mtime (newest first),
    walking until enough valid, deduplicated-by-canonical-game_dir entries are collected.
    """
    games = paths.games_dir()
    if not games.is_dir():
        return []

    files = [p for p in games.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    seen_keys: set[str] = set()
    out: list[RecentGameEntry] = []

    for path in files:
        if len(out) >= limit:
            break
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            log.warning("Skipping manifest %s: %s", path, e)
            continue
        if not isinstance(data, dict):
            log.warning("Skipping manifest %s: not a JSON object", path)
            continue
        gd_raw = data.get("game_dir")
        if gd_raw is None or not str(gd_raw).strip():
            continue
        key = _canonical_game_dir_key(str(gd_raw))
        if key is None:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)

        try:
            game_dir = canonical_game_dir(str(gd_raw))
        except OSError:
            continue
        name = _display_name_from_manifest(data)
        path_short = _shorten_path_display(str(game_dir))
        out.append(RecentGameEntry(game_dir=game_dir, display_name=name, path_short=path_short))

    return out
