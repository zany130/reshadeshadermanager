"""User repo catalog helpers."""

from __future__ import annotations

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.repos import add_user_repo, load_user_repos


def test_add_user_repo_persists(rsm_paths: RsmPaths) -> None:
    add_user_repo(
        rsm_paths,
        repo_id="my-pack",
        name="My Pack",
        git_url="https://example.com/me/shaders.git",
        author="me",
        description="test",
    )
    user = load_user_repos(rsm_paths)
    assert len(user) == 1
    assert user[0]["id"] == "my-pack"
    assert user[0]["source"] == "user"
    assert user[0]["git_url"] == "https://example.com/me/shaders.git"
