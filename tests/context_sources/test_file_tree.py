"""Tests for FileTreeContextSource."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigger.context_sources.file_tree import FileTreeContextSource


@pytest.fixture
def docs_tree(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide")
    sub = docs / "api"
    sub.mkdir()
    (sub / "endpoints.md").write_text("# Endpoints")
    return tmp_path


class TestGather:
    def test_returns_all_files(self, docs_tree: Path):
        src = FileTreeContextSource(root="docs")
        result = src.gather(docs_tree)
        names = sorted(p.name for p in result.files)
        assert names == ["endpoints.md", "guide.md"]

    def test_returns_empty_for_missing_required(self, tmp_path: Path):
        src = FileTreeContextSource(root="missing")
        result = src.gather(tmp_path)
        assert result.files == []

    def test_no_warning_for_missing_optional(self, tmp_path: Path, caplog):
        src = FileTreeContextSource(root="missing", required=False)
        result = src.gather(tmp_path)
        assert result.files == []
        assert "does not exist" not in caplog.text

    def test_warning_for_missing_required(self, tmp_path: Path, caplog):
        src = FileTreeContextSource(root="missing", required=True)
        src.gather(tmp_path)
        assert "does not exist" in caplog.text

    def test_file_not_dir(self, tmp_path: Path, caplog):
        (tmp_path / "docs").write_text("not a dir")
        src = FileTreeContextSource(root="docs")
        result = src.gather(tmp_path)
        assert result.files == []
        assert "not a directory" in caplog.text

    def test_empty_directory(self, tmp_path: Path):
        (tmp_path / "docs").mkdir()
        src = FileTreeContextSource(root="docs")
        result = src.gather(tmp_path)
        assert result.files == []

    def test_nested_files(self, tmp_path: Path):
        d = tmp_path / "src" / "a" / "b"
        d.mkdir(parents=True)
        (d / "deep.py").write_text("pass")
        src = FileTreeContextSource(root="src")
        result = src.gather(tmp_path)
        assert len(result.files) == 1
        assert result.files[0].name == "deep.py"


class TestProtocolConformance:
    def test_satisfies_context_source_protocol(self):
        from rigger._protocols import ContextSource

        source: ContextSource = FileTreeContextSource(root="x")
        assert hasattr(source, "gather")
