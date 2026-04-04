"""Format exceptions for user-facing messages (CLI, GTK dialogs, git, network)."""

from __future__ import annotations

import subprocess
import urllib.error


def format_exception_for_ui(exc: BaseException, *, max_chars: int = 2400) -> str:
    """
    Produce a readable message for common failure modes (git, HTTP, timeouts).
    """
    if isinstance(exc, subprocess.CalledProcessError):
        detail = (exc.stderr or exc.stdout or "").strip()
        if len(detail) > max_chars:
            detail = detail[: max_chars - 3] + "..."
        cmd = " ".join(getattr(exc, "cmd", ()) or ()) or "(unknown command)"
        base = f"Command failed (exit {exc.returncode}): {cmd}"
        if detail:
            return f"{base}\n\n{detail}"
        return base
    if isinstance(exc, TimeoutError):
        return f"The operation timed out: {exc}"
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP error {exc.code}: {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return f"Network error: {reason}"
        return f"Network error: {reason!s}"
    if isinstance(exc, OSError):
        return f"{type(exc).__name__}: {exc}"
    return str(exc)
