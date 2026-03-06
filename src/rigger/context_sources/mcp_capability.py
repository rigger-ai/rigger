"""McpCapabilityContextSource — reports MCP tool/server availability.

Config name: ``mcp_capability``

Corpus pattern CP-3: External issue tracker context (registration stub).
Sources: C3 (Anthropic Quickstart), C4 (Linear Harness).
"""

from __future__ import annotations

from pathlib import Path

from rigger._types import ProvisionResult


class McpCapabilityContextSource:
    """Reports MCP tool/server availability as a capability description.

    This is a registration stub — the MCP server is configured at SDK
    client creation time. ``gather()`` writes a capabilities file and
    returns a capability string for observability.

    Args:
        name: MCP server name (e.g. ``"linear"``, ``"puppeteer"``).
        description: Human-readable capability description.
        output: Output path relative to project root
            (default: ``".harness/capabilities.md"``).
    """

    def __init__(  # noqa: D107
        self,
        name: str,
        *,
        description: str = "",
        output: str = ".harness/capabilities.md",
    ) -> None:
        self._name = name
        self._description = description or f"MCP server: {name}"
        self._output = output

    def gather(self, project_root: Path) -> ProvisionResult:
        """Write capabilities file and return path + capability string.

        Creates or appends to the capabilities file at the configured
        output path. Returns the file path and a capability description
        for observability.
        """
        output_path = project_root / self._output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        entry = f"- **{self._name}**: {self._description}\n"

        if output_path.exists():
            existing = output_path.read_text(encoding="utf-8")
            if entry not in existing:
                output_path.write_text(existing + entry, encoding="utf-8")
        else:
            header = "# MCP Capabilities\n\n"
            output_path.write_text(header + entry, encoding="utf-8")

        return ProvisionResult(
            files=[output_path],
            capabilities=[self._description],
        )
