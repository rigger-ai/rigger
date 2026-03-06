"""Tests for DocStalenessEntropyDetector."""

from __future__ import annotations

import os
import time
from pathlib import Path

from rigger.entropy_detectors.doc_staleness import DocStalenessEntropyDetector

_SECONDS_PER_DAY = 86400


def _age_file(path: Path, days: int) -> None:
    """Set a file's mtime to ``days`` days ago."""
    old_time = time.time() - (days * _SECONDS_PER_DAY)
    os.utime(path, (old_time, old_time))


class TestScan:
    def test_detects_stale_files(self, tmp_path: Path):
        docs = tmp_path / "docs"
        docs.mkdir()
        stale = docs / "old.md"
        stale.write_text("old content")
        _age_file(stale, 60)

        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)

        assert len(tasks) == 1
        assert "old.md" in tasks[0].description
        assert tasks[0].metadata["source"] == "entropy_scan"
        assert tasks[0].metadata["age_days"] >= 59

    def test_ignores_fresh_files(self, tmp_path: Path):
        docs = tmp_path / "docs"
        docs.mkdir()
        fresh = docs / "new.md"
        fresh.write_text("fresh content")

        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_no_findings_when_no_matching_files(self, tmp_path: Path):
        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_multiple_patterns(self, tmp_path: Path):
        docs = tmp_path / "docs"
        docs.mkdir()
        readme = tmp_path / "README.md"

        stale_doc = docs / "guide.md"
        stale_doc.write_text("guide")
        _age_file(stale_doc, 45)

        readme.write_text("readme")
        _age_file(readme, 45)

        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md", "README.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)
        assert len(tasks) == 2

    def test_task_metadata_contains_file_info(self, tmp_path: Path):
        docs = tmp_path / "docs"
        docs.mkdir()
        stale = docs / "api.md"
        stale.write_text("api docs")
        _age_file(stale, 90)

        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)

        assert len(tasks) == 1
        assert tasks[0].metadata["file"] == "docs/api.md"
        assert "last_modified" in tasks[0].metadata
        assert tasks[0].metadata["age_days"] >= 89

    def test_task_id_includes_relative_path(self, tmp_path: Path):
        docs = tmp_path / "docs"
        docs.mkdir()
        stale = docs / "index.md"
        stale.write_text("index")
        _age_file(stale, 40)

        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)
        assert tasks[0].id == "stale-docs/index.md"

    def test_skips_directories_matching_pattern(self, tmp_path: Path):
        docs = tmp_path / "docs"
        # Create a directory that ends with .md (edge case)
        weird = docs / "subdir.md"
        weird.mkdir(parents=True)

        detector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_custom_max_age(self, tmp_path: Path):
        docs = tmp_path / "docs"
        docs.mkdir()
        f = docs / "recent.md"
        f.write_text("content")
        _age_file(f, 10)

        # 30 days: not stale
        detector30 = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=30
        )
        assert detector30.scan(tmp_path) == []

        # 7 days: stale
        detector7 = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"], max_age_days=7
        )
        tasks = detector7.scan(tmp_path)
        assert len(tasks) == 1


class TestProtocolConformance:
    def test_satisfies_entropy_detector_protocol(self):
        from rigger._protocols import EntropyDetector

        detector: EntropyDetector = DocStalenessEntropyDetector(
            patterns=["docs/**/*.md"]
        )
        assert hasattr(detector, "scan")
