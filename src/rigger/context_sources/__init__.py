"""Built-in ContextSource implementations for common context provisioning patterns."""

from rigger.context_sources.agents_md import AgentsMdContextSource
from rigger.context_sources.file_tree import FileTreeContextSource
from rigger.context_sources.mcp_capability import McpCapabilityContextSource
from rigger.context_sources.static_files import StaticFilesContextSource

__all__ = [
    "AgentsMdContextSource",
    "FileTreeContextSource",
    "McpCapabilityContextSource",
    "StaticFilesContextSource",
]
