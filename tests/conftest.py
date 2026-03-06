"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def git_project(tmp_path: Path) -> Path:
    """A tmp_path initialized as a git repo with an initial commit."""
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@rigger.dev"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Rigger Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create initial commit so HEAD exists
    (tmp_path / ".gitkeep").touch()
    subprocess.run(
        ["git", "add", "."],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


@pytest.fixture()
def task_file(git_project: Path) -> Path:
    """Creates tasks.json with 3 sample tasks in git_project, returns its path."""
    tasks = [
        {"id": "t1", "description": "Add feature one", "status": "pending"},
        {"id": "t2", "description": "Add feature two", "status": "pending"},
        {"id": "t3", "description": "Add feature three", "status": "pending"},
    ]
    path = git_project / "tasks.json"
    path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def stories_file(git_project: Path) -> Path:
    """Creates stories.json with 3 stories in PRD format, returns its path."""
    data = {
        "stories": [
            {"id": "s1", "description": "User can sign up", "status": "pending"},
            {"id": "s2", "description": "User can log in", "status": "pending"},
            {"id": "s3", "description": "User can reset password", "status": "pending"},
        ]
    }
    path = git_project / "stories.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
