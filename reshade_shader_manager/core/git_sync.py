"""Git clone/pull with in-process serialization (v0.1)."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

from reshade_shader_manager.core.paths import RsmPaths

log = logging.getLogger(__name__)

_git_lock = threading.Lock()


def clone_or_pull(repo_dir: Path, git_url: str, *, timeout: float = 300.0, pull: bool = True) -> None:
    """
    If ``repo_dir`` is missing or not a git working tree, ``git clone`` into ``repo_dir``.

    If it is already a clone and ``pull`` is True, run ``git pull --rebase=false``.
    If ``pull`` is False, an existing clone is left as-is (no fetch/pull).
    """
    repo_dir = repo_dir.resolve()
    with _git_lock:
        git_dir = repo_dir / ".git"
        if git_dir.exists():
            if pull:
                log.info("git pull in %s", repo_dir)
                subprocess.run(
                    ["git", "-C", str(repo_dir), "pull", "--rebase=false"],
                    check=True,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                )
            else:
                log.debug("Skipping git pull for existing repo %s", repo_dir)
        else:
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            log.info("git clone %s -> %s", git_url, repo_dir)
            subprocess.run(
                ["git", "clone", git_url, str(repo_dir)],
                check=True,
                timeout=timeout,
                capture_output=True,
                text=True,
            )


def pull_existing_clones_for_catalog(
    paths: RsmPaths,
    catalog: list[dict[str, str]],
    *,
    timeout: float = 300.0,
) -> list[str]:
    """
    For each entry in ``catalog``, if ``paths.repo_clone_dir(id)`` already has
    ``.git``, run ``git pull``. Missing clones are skipped (no clone).

    Returns a list of ``\"<repo_id>: <message>\"`` for failures; empty if every
    pull succeeded or there was nothing to pull.
    """
    failures: list[str] = []
    for r in catalog:
        rid = r.get("id", "").strip()
        url = (r.get("git_url") or "").strip()
        if not rid or not url:
            continue
        d = paths.repo_clone_dir(rid)
        if not (d / ".git").exists():
            continue
        try:
            clone_or_pull(d, url, pull=True, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{rid}: {e}")
    return failures


def ensure_plugin_addon_clone(
    paths: RsmPaths,
    addon_id: str,
    git_url: str,
    *,
    pull: bool = True,
    timeout: float = 300.0,
) -> None:
    """
    Clone or update the global git cache for a **repo-based** plugin add-on.

    Uses :meth:`RsmPaths.plugin_addon_clone_dir` (``…/plugin-addons/<id>/``). Same
    semantics as shader :func:`clone_or_pull` for ``repos/<id>/``.
    """
    d = paths.plugin_addon_clone_dir(addon_id)
    clone_or_pull(d, git_url.strip(), pull=pull, timeout=timeout)


def pull_existing_plugin_addon_clones(
    paths: RsmPaths,
    addon_catalog: list[dict[str, str]],
    *,
    timeout: float = 300.0,
) -> list[str]:
    """
    For each **repo-mode** entry in ``addon_catalog``, if
    ``plugin_addon_clone_dir(id)`` already has ``.git``, run ``git pull``.

    Missing clones are skipped (no clone). Returns ``\"<id>: <message>\"`` for failures.
    """
    failures: list[str] = []
    for r in addon_catalog:
        if r.get("install_mode") != "repo":
            continue
        aid = (r.get("id") or "").strip()
        url = (r.get("repository_url") or "").strip()
        if not aid or not url:
            continue
        d = paths.plugin_addon_clone_dir(aid)
        if not (d / ".git").exists():
            continue
        try:
            clone_or_pull(d, url, pull=True, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{aid}: {e}")
    return failures


def pull_shader_and_plugin_addon_clones(
    paths: RsmPaths,
    *,
    shader_catalog: list[dict[str, str]] | None,
    plugin_addon_catalog: list[dict[str, str]] | None,
    timeout: float = 300.0,
) -> list[str]:
    """
    Run :func:`pull_existing_clones_for_catalog` and
    :func:`pull_existing_plugin_addon_clones` when the corresponding catalog is non-empty.

    Returns concatenated failure lines (shader repos first, then plugin add-ons).
    """
    failures: list[str] = []
    if shader_catalog:
        failures.extend(
            pull_existing_clones_for_catalog(paths, shader_catalog, timeout=timeout)
        )
    if plugin_addon_catalog:
        failures.extend(
            pull_existing_plugin_addon_clones(paths, plugin_addon_catalog, timeout=timeout)
        )
    return failures
