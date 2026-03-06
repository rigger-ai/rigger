"""Tests for McpCapabilityContextSource."""

from __future__ import annotations

from pathlib import Path

from rigger.context_sources.mcp_capability import McpCapabilityContextSource


class TestGather:
    def test_creates_capabilities_file(self, tmp_path: Path):
        src = McpCapabilityContextSource(name="linear")
        result = src.gather(tmp_path)
        assert len(result.files) == 1
        output = tmp_path / ".harness" / "capabilities.md"
        assert output.exists()
        content = output.read_text()
        assert "linear" in content

    def test_returns_capability_string(self, tmp_path: Path):
        src = McpCapabilityContextSource(
            name="puppeteer", description="Browser automation via Puppeteer"
        )
        result = src.gather(tmp_path)
        assert len(result.capabilities) == 1
        assert "Browser automation via Puppeteer" in result.capabilities[0]

    def test_default_description(self, tmp_path: Path):
        src = McpCapabilityContextSource(name="linear")
        result = src.gather(tmp_path)
        assert "MCP server: linear" in result.capabilities[0]

    def test_appends_to_existing(self, tmp_path: Path):
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        caps = harness_dir / "capabilities.md"
        caps.write_text("# MCP Capabilities\n\n- **old**: Old server\n")

        src = McpCapabilityContextSource(name="new_tool")
        src.gather(tmp_path)

        content = caps.read_text()
        assert "old" in content
        assert "new_tool" in content

    def test_no_duplicate_entries(self, tmp_path: Path):
        src = McpCapabilityContextSource(name="linear")
        src.gather(tmp_path)
        src.gather(tmp_path)

        output = tmp_path / ".harness" / "capabilities.md"
        content = output.read_text()
        assert content.count("- **linear**") == 1

    def test_custom_output_path(self, tmp_path: Path):
        src = McpCapabilityContextSource(name="test", output="context/mcp.md")
        result = src.gather(tmp_path)
        assert result.files[0] == tmp_path / "context" / "mcp.md"
        assert (tmp_path / "context" / "mcp.md").exists()

    def test_creates_parent_dirs(self, tmp_path: Path):
        src = McpCapabilityContextSource(name="test", output="deep/nested/caps.md")
        src.gather(tmp_path)
        assert (tmp_path / "deep" / "nested" / "caps.md").exists()


class TestProtocolConformance:
    def test_satisfies_context_source_protocol(self):
        from rigger._protocols import ContextSource

        source: ContextSource = McpCapabilityContextSource(name="x")
        assert hasattr(source, "gather")
