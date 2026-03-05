"""WorkspaceManager implementations for agent isolation."""

from rigger.workspace.git_worktree import GitWorktreeManager
from rigger.workspace.independent import IndependentDirManager

__all__ = ["GitWorktreeManager", "IndependentDirManager"]
