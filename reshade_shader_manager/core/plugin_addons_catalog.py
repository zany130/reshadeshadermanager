"""Fetch official ``Addons.ini``, cache under XDG cache, return normalized upstream list."""

from __future__ import annotations

import configparser
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_parse import parse_and_normalize_addons_ini

log = logging.getLogger(__name__)

ADDONS_INI_URL = (
    "https://raw.githubusercontent.com/crosire/reshade-shaders/list/Addons.ini"
)
USER_AGENT = "reshade-shader-manager/0.2 (plugin add-ons catalog; +https://github.com/)"


def _http_get(url: str, *, timeout: float = 45.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def fetch_addons_ini_raw() -> tuple[str | None, str | None]:
    """Return ``(text, error_message)``."""
    try:
        raw = _http_get(ADDONS_INI_URL)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeError) as e:
        return None, str(e)
    try:
        return raw.decode("utf-8"), None
    except UnicodeError as e:
        return None, str(e)


def load_plugin_addons_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def save_plugin_addons_cache(path: Path, addons: list[dict[str, str]], fetch_error: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": ADDONS_INI_URL,
        "addons": addons,
    }
    if fetch_error:
        payload["fetch_error"] = fetch_error
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def cache_is_fresh(path: Path, ttl_hours: float) -> bool:
    data = load_plugin_addons_cache(path)
    if not data:
        return False
    ts = data.get("fetched_at_utc")
    if not isinstance(ts, str):
        return False
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    age_sec = time.time() - parsed.timestamp()
    return age_sec < ttl_hours * 3600.0


def _addons_from_cache_payload(data: dict[str, Any]) -> list[dict[str, str]]:
    raw = data.get("addons")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append({str(k): str(v) if v is not None else "" for k, v in item.items()})
    return out


def get_upstream_plugin_addons(
    paths: RsmPaths,
    *,
    ttl_hours: float,
    force_refresh: bool = False,
) -> list[dict[str, str]]:
    """
    Return normalized upstream plugin add-ons, refreshing ``Addons.ini`` when stale.

    On fetch failure, returns the last cached list if present; otherwise ``[]``.
    """
    cache_path = paths.plugin_addons_cache_path()
    if not force_refresh and cache_is_fresh(cache_path, ttl_hours):
        data = load_plugin_addons_cache(cache_path)
        if data:
            return _addons_from_cache_payload(data)

    text, err = fetch_addons_ini_raw()
    if text is None:
        stale = load_plugin_addons_cache(cache_path)
        payload = _addons_from_cache_payload(stale) if stale else []
        if payload:
            log.warning("Plugin add-on catalog fetch failed; using stale cache")
            return payload
        if err:
            log.warning("Plugin add-on catalog fetch failed and no cache: %s", err)
        save_plugin_addons_cache(cache_path, [], err)
        return []

    addons: list[dict[str, str]] = []
    combined_err: str | None = err
    try:
        addons = parse_and_normalize_addons_ini(text)
    except (configparser.Error, ValueError) as e:
        pe = f"parse error: {e}"
        combined_err = f"{combined_err}; {pe}" if combined_err else pe
        log.warning("Addons.ini parse failed: %s", e)
    save_plugin_addons_cache(cache_path, addons, combined_err)
    return addons
