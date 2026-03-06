"""Tests for StaticFilesContextSource."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigger.context_sources.static_files import StaticFilesContextSource


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    src = tmp_path / "source_data"
    src.mkdir()
    (src / "config.json").write_text('{"key": "value"}')
    sub = src / "templates"
    sub.mkdir()
    (sub / "main.txt").write_text("template content")
    return src


class TestGatherFile:
    def test_copies_single_file(self, tmp_path: Path):
        src_file = tmp_path / "input.txt"
        src_file.write_text("hello")
        src = StaticFilesContextSource(source=str(src_file), destination="output.txt")
        result = src.gather(tmp_path)
        assert len(result.files) == 1
        dest = tmp_path / "output.txt"
        assert dest.exists()
        assert dest.read_text() == "hello"

    def test_missing_source_file(self, tmp_path: Path, caplog):
        src = StaticFilesContextSource(
            source="/nonexistent/file.txt", destination="output.txt"
        )
        result = src.gather(tmp_path)
        assert result.files == []
        assert "does not exist" in caplog.text

    def test_creates_parent_directories(self, tmp_path: Path):
        src_file = tmp_path / "input.txt"
        src_file.write_text("data")
        src = StaticFilesContextSource(
            source=str(src_file), destination="deep/nested/output.txt"
        )
        src.gather(tmp_path)
        assert (tmp_path / "deep" / "nested" / "output.txt").exists()


class TestGatherDirectory:
    def test_copies_directory_tree(self, source_dir: Path, tmp_path: Path):
        src = StaticFilesContextSource(source=str(source_dir), destination="dest")
        result = src.gather(tmp_path)
        assert len(result.files) == 2
        names = sorted(p.name for p in result.files)
        assert names == ["config.json", "main.txt"]

    def test_preserves_directory_structure(self, source_dir: Path, tmp_path: Path):
        src = StaticFilesContextSource(source=str(source_dir), destination="dest")
        src.gather(tmp_path)
        assert (tmp_path / "dest" / "config.json").exists()
        assert (tmp_path / "dest" / "templates" / "main.txt").exists()

    def test_preserves_file_content(self, source_dir: Path, tmp_path: Path):
        src = StaticFilesContextSource(source=str(source_dir), destination="dest")
        src.gather(tmp_path)
        content = (tmp_path / "dest" / "config.json").read_text()
        assert '"key"' in content

    def test_empty_source_directory(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        src = StaticFilesContextSource(source=str(empty), destination="dest")
        result = src.gather(tmp_path)
        assert result.files == []

    def test_relative_source_path(self, tmp_path: Path):
        src_dir = tmp_path / "rel_src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("relative")
        src = StaticFilesContextSource(source="rel_src", destination="dest")
        result = src.gather(tmp_path)
        assert len(result.files) == 1
        assert (tmp_path / "dest" / "file.txt").read_text() == "relative"


class TestProtocolConformance:
    def test_satisfies_context_source_protocol(self):
        from rigger._protocols import ContextSource

        source: ContextSource = StaticFilesContextSource(source="x", destination="y")
        assert hasattr(source, "gather")
