"""PCGamingWiki shader repo list: fetch, cache, coarse HTML parse."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.repos import validate_repo_id

log = logging.getLogger(__name__)

PCGW_API = (
    "https://www.pcgamingwiki.com/w/api.php?"
    + urllib.parse.urlencode(
        {
            "action": "parse",
            "page": "ReShade",
            "format": "json",
            "prop": "text",
        }
    )
)
def _user_agent() -> str:
    try:
        ver = version("reshade-shader-manager")
    except PackageNotFoundError:
        ver = "0.0.0"
    return f"reshade-shader-manager/{ver} (PCGW repo list; +https://github.com/)"


USER_AGENT = _user_agent()


def _http_get(url: str, *, timeout: float = 45.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _slug_repo_id_from_url(git_url: str) -> str:
    u = git_url.rstrip("/").removesuffix(".git")
    parts = u.split("/")
    if len(parts) >= 2:
        base = parts[-1].lower()
    else:
        base = "repo"
    base = re.sub(r"[^a-z0-9_-]+", "-", base).strip("-") or "repo"
    if not base[0].isalnum():
        base = "r-" + base
    if len(base) > 48:
        base = base[:48].rstrip("-")
    validate_repo_id(base)
    return base


def parse_pcgw_repos_from_html(html: str) -> list[dict[str, str]]:
    """
    Best-effort: find GitHub git URLs and synthesize ids.

    May return duplicates filtered by id later.
    """
    repos: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="(https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)(?:\.git)?"',
        html,
    ):
        url = m.group(1)
        if "/releases" in url or "/issues" in url:
            continue
        git_url = url if url.endswith(".git") else url + ".git"
        try:
            rid = _slug_repo_id_from_url(git_url)
        except ValueError:
            rid = re.sub(r"[^a-z0-9_-]", "-", url.split("/")[-1].lower())[:48]
            if not rid or not rid[0].isalnum():
                continue
        if rid in seen:
            continue
        seen.add(rid)
        name = url.rstrip("/").split("/")[-1]
        repos.append(
            {
                "id": rid,
                "name": name,
                "git_url": git_url,
                "author": "",
                "description": "",
                "source": "pcgw",
            }
        )
    return repos


def fetch_pcgw_repos_raw() -> tuple[list[dict[str, str]], str | None]:
    """Return (repos, error_message_or_none)."""
    try:
        raw = _http_get(PCGW_API)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeError) as e:
        return [], str(e)
    except json.JSONDecodeError as e:
        return [], f"JSON decode error: {e}"
    try:
        text = data["parse"]["text"]["*"]
    except (KeyError, TypeError) as e:
        return [], f"unexpected PCGW JSON shape: {e}"
    if not isinstance(text, str):
        return [], "PCGW parse text is not a string"
    return parse_pcgw_repos_from_html(text), None


def load_pcgw_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def save_pcgw_cache(path: Path, repos: list[dict[str, str]], error: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "repos": repos,
    }
    if error:
        payload["raw_parse_error"] = error
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def cache_is_fresh(path: Path, ttl_hours: float) -> bool:
    data = load_pcgw_cache(path)
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


def get_pcgw_repos(paths: RsmPaths, *, ttl_hours: float, force_refresh: bool = False) -> list[dict[str, str]]:
    """
    Return cached PCGW repo list, refreshing if stale or ``force_refresh``.

    On network failure, returns last cache if any; otherwise empty list.
    """
    cache_path = paths.pcgw_cache_path()
    if not force_refresh and cache_is_fresh(cache_path, ttl_hours):
        data = load_pcgw_cache(cache_path)
        if data and isinstance(data.get("repos"), list):
            return [r for r in data["repos"] if isinstance(r, dict)]

    repos, err = fetch_pcgw_repos_raw()
    if repos or err is not None:
        save_pcgw_cache(cache_path, repos, err)
    if repos:
        return repos
    stale = load_pcgw_cache(cache_path)
    if stale and isinstance(stale.get("repos"), list):
        log.warning("PCGW fetch failed; using stale cache")
        return [r for r in stale["repos"] if isinstance(r, dict)]
    log.warning("PCGW fetch failed and no cache")
    return []
