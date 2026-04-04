"""Parse official ReShade ``Addons.ini`` into normalized plugin add-on records (no I/O)."""

from __future__ import annotations

import configparser
import hashlib
import re
from typing import Any, Mapping

from reshade_shader_manager.core.repos import validate_repo_id


def _slugify_package_name(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if s and not s[0].isalpha():
        s = "a-" + s
    return s or "addon"


def stable_plugin_addon_id(
    *,
    package_name: str,
    repository_url: str,
    download_url_32: str,
    download_url_64: str,
    download_url: str,
) -> str:
    """
    Stable id from package name + repo + download URLs (not ``Addons.ini`` section index).

    Uses the same character rules as shader ``repo`` ids (``validate_repo_id``).
    """
    slug = _slugify_package_name(package_name)[:40].strip("-") or "addon"
    payload = "\n".join(
        [
            repository_url.strip().lower(),
            download_url_32.strip().lower(),
            download_url_64.strip().lower(),
            download_url.strip().lower(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    candidate = f"{slug}-{digest}"
    if len(candidate) > 64:
        candidate = candidate[:64].rstrip("-")
    try:
        validate_repo_id(candidate)
    except ValueError:
        candidate = f"addon-{digest}"
        if len(candidate) > 64:
            candidate = candidate[:64].rstrip("-")
        validate_repo_id(candidate)
    return candidate


def _filter_addons_ini_comment_lines(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _raw_section_has_download_urls(raw: dict[str, str]) -> bool:
    """True if the section lists at least one of DownloadUrl32 / DownloadUrl64 / DownloadUrl."""
    return bool(
        raw.get("downloadurl32", "").strip()
        or raw.get("downloadurl64", "").strip()
        or raw.get("downloadurl", "").strip()
    )


def parse_addons_ini_sections(text: str) -> list[tuple[str, dict[str, str]]]:
    """Return ``(section_name, lowercased_key -> value)`` for each INI section."""
    body = _filter_addons_ini_comment_lines(text)
    cp: configparser.ConfigParser = configparser.ConfigParser()
    cp.read_string(body)
    out: list[tuple[str, dict[str, str]]] = []
    for sec in cp.sections():
        raw = {str(k).lower(): str(v).strip() for k, v in cp.items(sec)}
        out.append((sec, raw))
    return out


def normalize_upstream_plugin_addon(
    upstream_section: str,
    raw: dict[str, str],
) -> dict[str, str]:
    """One catalog row; ``source`` is ``upstream``."""
    name = raw.get("packagename", "").strip()
    desc = raw.get("packagedescription", "").strip()
    u32 = raw.get("downloadurl32", "").strip()
    u64 = raw.get("downloadurl64", "").strip()
    u1 = raw.get("downloadurl", "").strip()
    repo = raw.get("repositoryurl", "").strip()
    effect = raw.get("effectinstallpath", "").strip()
    pid = stable_plugin_addon_id(
        package_name=name or f"section-{upstream_section}",
        repository_url=repo,
        download_url_32=u32,
        download_url_64=u64,
        download_url=u1,
    )
    return {
        "id": pid,
        "name": name or pid,
        "description": desc,
        "download_url_32": u32,
        "download_url_64": u64,
        "download_url": u1,
        "repository_url": repo,
        "effect_install_path": effect,
        "upstream_section": upstream_section,
        "source": "upstream",
        "install_mode": "artifact",
        "dll_32_path": "",
        "dll_64_path": "",
        "shader_root": "",
        "companion_shader_paths": "",
    }


def parse_and_normalize_addons_ini(text: str) -> list[dict[str, str]]:
    """
    Parse full ``Addons.ini`` body into normalized upstream entries.

    Drops sections without ``PackageName``, sections with **no download URLs** (repository-only
    metadata like Geo3D / PyHook), then de-duplicates by stable ``id`` (first wins).
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for sec, raw in parse_addons_ini_sections(text):
        if not raw.get("packagename", "").strip():
            continue
        if not _raw_section_has_download_urls(raw):
            continue
        row = normalize_upstream_plugin_addon(sec, raw)
        rid = row["id"]
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def assert_plugin_addon_row(m: Mapping[str, Any]) -> dict[str, str]:
    """
    Validate keys for a catalog row (upstream or user).

    **v0.2:** ``install_mode`` is ``artifact`` (download URLs) or ``repo`` (git clone +
    ``dll_32_path`` / ``dll_64_path``). Empty ``install_mode`` defaults to ``artifact``.
    """
    required = (
        "id",
        "name",
        "description",
        "download_url_32",
        "download_url_64",
        "download_url",
        "repository_url",
        "effect_install_path",
        "upstream_section",
        "source",
    )
    optional = (
        "install_mode",
        "dll_32_path",
        "dll_64_path",
        "shader_root",
        "companion_shader_paths",
    )
    d = {k: str(m.get(k, "") if m.get(k, "") is not None else "") for k in required}
    for k in optional:
        d[k] = str(m.get(k, "") if m.get(k, "") is not None else "").strip()
    validate_repo_id(d["id"].strip().lower())
    d["id"] = d["id"].strip().lower()
    if d["source"] not in ("upstream", "user"):
        raise ValueError(f"invalid source: {d['source']!r}")
    mode = (d.get("install_mode") or "").strip().lower() or "artifact"
    if mode not in ("artifact", "repo"):
        raise ValueError(f"invalid install_mode: {d['install_mode']!r} (expected 'artifact' or 'repo')")
    d["install_mode"] = mode
    if mode == "repo":
        if not d["repository_url"].strip():
            raise ValueError("install_mode=repo requires a non-empty repository_url")
        if not (d["dll_32_path"].strip() or d["dll_64_path"].strip()):
            raise ValueError("install_mode=repo requires at least one of dll_32_path, dll_64_path")
    return d
