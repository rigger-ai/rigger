"""Tests for AgentsMdContextSource."""

from __future__ import annotations

from pathlib import Path

from rigger.context_sources.agents_md import AgentsMdContextSource


class TestGather:
    def test_inline_template(self, tmp_path: Path):
        src = AgentsMdContextSource(template="# Project\n\nHello world")
        result = src.gather(tmp_path)
        assert len(result.files) == 1
        assert result.files[0] == tmp_path / "AGENTS.md"
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Hello world" in content

    def test_variable_substitution(self, tmp_path: Path):
        src = AgentsMdContextSource(
            template="Task: {task}\nConstraints: {constraints}\nContext: {context}"
        )
        src.gather(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Task: " in content
        assert "Constraints: " in content

    def test_custom_variables(self, tmp_path: Path):
        src = AgentsMdContextSource(
            template="Project: {project_name}",
            variables={"project_name": "rigger"},
        )
        src.gather(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Project: rigger" in content

    def test_file_template(self, tmp_path: Path):
        tpl = tmp_path / "template.md"
        tpl.write_text("# {task}\n\nGenerated from template")
        src = AgentsMdContextSource(template=str(tpl))
        src.gather(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Generated from template" in content

    def test_relative_file_template(self, tmp_path: Path):
        tpl = tmp_path / "templates" / "agents.md"
        tpl.parent.mkdir()
        tpl.write_text("# Agents\n\n{context}")
        src = AgentsMdContextSource(template="templates/agents.md")
        result = src.gather(tmp_path)
        assert len(result.files) == 1

    def test_missing_template_file(self, tmp_path: Path, caplog):
        src = AgentsMdContextSource(template="/nonexistent/template.md")
        result = src.gather(tmp_path)
        assert result.files == []
        assert "does not exist" in caplog.text

    def test_custom_output_path(self, tmp_path: Path):
        src = AgentsMdContextSource(template="# Custom", output="docs/AGENTS.md")
        result = src.gather(tmp_path)
        assert result.files[0] == tmp_path / "docs" / "AGENTS.md"
        assert (tmp_path / "docs" / "AGENTS.md").exists()

    def test_overwrites_existing(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("old content")
        src = AgentsMdContextSource(template="new content")
        src.gather(tmp_path)
        assert (tmp_path / "AGENTS.md").read_text() == "new content"

    def test_unresolved_placeholders_preserved(self, tmp_path: Path):
        src = AgentsMdContextSource(template="Hello {unknown}")
        src.gather(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "{unknown}" in content


class TestProtocolConformance:
    def test_satisfies_context_source_protocol(self):
        from rigger._protocols import ContextSource

        source: ContextSource = AgentsMdContextSource(template="x")
        assert hasattr(source, "gather")
