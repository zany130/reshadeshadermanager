"""Session log file under XDG data (``logs/rsm.log``)."""

import logging
from pathlib import Path

import pytest

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.ui.log_view import attach_file_logging


def test_logs_dir_under_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    p = RsmPaths.from_env()
    assert p.logs_dir() == p.data_dir / "logs"


def test_attach_file_logging_writes_rsm_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = RsmPaths.from_env()
    paths.ensure_layout()
    h = attach_file_logging(paths)
    assert h is not None
    try:
        logging.getLogger("rsm.test_file").info("hello log file")
        log_file = paths.logs_dir() / "rsm.log"
        text = log_file.read_text(encoding="utf-8")
        assert "hello log file" in text
    finally:
        logging.getLogger().removeHandler(h)
