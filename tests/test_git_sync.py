"""Tests for git_sync helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from reshade_shader_manager.core.git_sync import (
    pull_existing_clones_for_catalog,
    pull_existing_plugin_addon_clones,
)
from reshade_shader_manager.core.paths import RsmPaths


def test_pull_existing_skips_when_no_clone(
    rsm_paths: RsmPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str]] = []

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        calls.append((repo_dir, git_url))

    monkeypatch.setattr(
        "reshade_shader_manager.core.git_sync.clone_or_pull",
        _fake,
    )
    catalog = [{"id": "noclone", "git_url": "https://example.com/x.git"}]
    assert pull_existing_clones_for_catalog(rsm_paths, catalog) == []
    assert calls == []


def test_pull_existing_runs_when_git_present(
    rsm_paths: RsmPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str]] = []

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        calls.append((repo_dir, git_url))

    monkeypatch.setattr(
        "reshade_shader_manager.core.git_sync.clone_or_pull",
        _fake,
    )
    d = rsm_paths.repo_clone_dir("hasgit")
    d.mkdir(parents=True)
    (d / ".git").mkdir()
    catalog = [{"id": "hasgit", "git_url": "https://example.com/h.git"}]
    assert pull_existing_clones_for_catalog(rsm_paths, catalog) == []
    assert len(calls) == 1
    assert calls[0][0] == d
    assert calls[0][1] == "https://example.com/h.git"


def test_pull_plugin_addon_skips_non_repo_rows(
    rsm_paths: RsmPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str]] = []

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        calls.append((repo_dir, git_url))

    monkeypatch.setattr("reshade_shader_manager.core.git_sync.clone_or_pull", _fake)
    catalog = [
        {
            "id": "artifact",
            "install_mode": "artifact",
            "repository_url": "https://example.com/a.git",
        }
    ]
    assert pull_existing_plugin_addon_clones(rsm_paths, catalog) == []
    assert calls == []


def test_pull_plugin_addon_skips_when_no_clone(
    rsm_paths: RsmPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str]] = []

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        calls.append((repo_dir, git_url))

    monkeypatch.setattr("reshade_shader_manager.core.git_sync.clone_or_pull", _fake)
    catalog = [
        {
            "id": "norepo",
            "install_mode": "repo",
            "repository_url": "https://example.com/x.git",
        }
    ]
    assert pull_existing_plugin_addon_clones(rsm_paths, catalog) == []
    assert calls == []


def test_pull_plugin_addon_runs_when_git_present(
    rsm_paths: RsmPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str]] = []

    def _fake(repo_dir: Path, git_url: str, **kwargs: object) -> None:
        calls.append((repo_dir, git_url))

    monkeypatch.setattr("reshade_shader_manager.core.git_sync.clone_or_pull", _fake)
    aid = "pa1"
    d = rsm_paths.plugin_addon_clone_dir(aid)
    d.mkdir(parents=True)
    (d / ".git").mkdir()
    catalog = [
        {
            "id": aid,
            "install_mode": "repo",
            "repository_url": "https://example.com/pa.git",
        }
    ]
    assert pull_existing_plugin_addon_clones(rsm_paths, catalog) == []
    assert len(calls) == 1
    assert calls[0][0] == d
    assert calls[0][1] == "https://example.com/pa.git"
