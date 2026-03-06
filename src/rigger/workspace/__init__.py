"""WorkspaceManager implementations for agent isolation."""

from rigger.workspace.git_worktree import GitWorktreeManager
from rigger.workspace.independent import IndependentDirManager
from rigger.workspace.independent_branch import IndependentBranchManager

__all__ = ["GitWorktreeManager", "IndependentBranchManager", "IndependentDirManager"]
