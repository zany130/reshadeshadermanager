"""Git clone/pull with in-process serialization (v0.1)."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_git_lock = threading.Lock()


def clone_or_pull(repo_dir: Path, git_url: str, *, timeout: float = 300.0) -> None:
    """
    If ``repo_dir`` is a git working tree, ``git pull --rebase=false``;
    otherwise ``git clone`` into ``repo_dir``.
    """
    repo_dir = repo_dir.resolve()
    with _git_lock:
        git_dir = repo_dir / ".git"
        if git_dir.exists():
            log.info("git pull in %s", repo_dir)
            subprocess.run(
                ["git", "-C", str(repo_dir), "pull", "--rebase=false"],
                check=True,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
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
