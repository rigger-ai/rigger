"""Integration tests for entropy detectors — B5."""

import os
import time

from rigger.entropy_detectors import (
    DocStalenessEntropyDetector,
    ShellCommandEntropyDetector,
)


def test_doc_staleness_finds_old_files(git_project):
    docs_dir = git_project / "docs"
    docs_dir.mkdir()
    guide = docs_dir / "guide.md"
    guide.write_text("# Guide\nSome content.\n")

    # Set mtime to 60 days ago
    old_time = time.time() - (60 * 86400)
    os.utime(guide, (old_time, old_time))

    detector = DocStalenessEntropyDetector(patterns=["docs/**/*.md"], max_age_days=30)
    tasks = detector.scan(git_project)

    assert len(tasks) >= 1
    assert "stale-" in tasks[0].id
    assert "guide.md" in tasks[0].description


def test_shell_command_parses_json(git_project):
    detector = ShellCommandEntropyDetector(
        command='echo \'[{"description":"fix docs"}]\''
    )
    tasks = detector.scan(git_project)

    assert len(tasks) == 1
    assert tasks[0].description == "fix docs"
    assert tasks[0].id == "entropy-0"
