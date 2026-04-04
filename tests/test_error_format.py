"""error_format helper."""

from __future__ import annotations

import subprocess

from reshade_shader_manager.core.error_format import format_exception_for_ui


def test_format_called_process_error_includes_stderr() -> None:
    exc = subprocess.CalledProcessError(
        1,
        ["git", "pull"],
        stderr="fatal: not a git repository",
    )
    out = format_exception_for_ui(exc)
    assert "exit 1" in out
    assert "fatal: not a git repository" in out


def test_format_urllib_error() -> None:
    import urllib.error

    exc = urllib.error.URLError("Name or service not known")
    out = format_exception_for_ui(exc)
    assert "Network error" in out
