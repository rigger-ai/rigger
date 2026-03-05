"""Dimension protocols — extension point interfaces for Rigger.

Each of the 6 harness dimensions is backed by a typing.Protocol, plus the
AgentBackend protocol for the opaque coding agent. These are the extension
points that harness authors implement.

Source: Strawman API v2 §2 (Task 5.2), ContextSource Lifecycle (Task 5.1),
ContextSource Boundary (Task 5.11).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from rigger._types import (
    EpochState,
    MergeResult,
    ProvisionResult,
    Task,
    TaskResult,
    VerifyResult,
)

# ─── Dimension Protocols ────────────────────────────────────────


class TaskSource(Protocol):
    """TD: Provides the next task(s) to execute."""

    def pending(self, project_root: Path) -> list[Task]:
        """Return pending tasks in priority order."""
        ...

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        """Update task status after execution."""
        ...


class ContextSource(Protocol):
    """CP: Prepares one aspect of the agent's information environment.

    A ContextSource discovers, verifies, or creates filesystem artifacts
    that provide context to the coding agent. The agent finds and reads
    these artifacts during execution; the ContextSource ensures they exist.

    DELIVERY BOUNDARY (Task 1.18, formalized in Task 5.11):
    ContextSource.gather() provisions DISCOVERABLE content — artifacts
    that the agent MAY find and read through its own tools during
    execution. It does NOT provision GUARANTEED-IN-PROMPT content.

    The guarantee of prompt inclusion is a delivery concern owned by:
    - AgentBackend: for always-loaded files (CLAUDE.md, AGENTS.md)
      via backend-specific mechanisms (e.g., setting_sources=["project"])
    - TaskSource: for task specifications that may include embedded
      domain context (Task.description dual-use, Task 1.18 Section 5)

    FILESYSTEM SCOPE (Task 5.11):
    gather() writes to project_root/ (or subdirectories thereof).
    It MUST NOT write to .harness/ — that directory is Rigger-managed
    and follows a versioned bilateral protocol (Task 5.3).

    LIFECYCLE: This protocol has NO lifecycle hooks (Task 5.1 decision).
    Setup and teardown of infrastructure is handled by:
    - Python context managers for per-harness scope
    - WorkspaceManager decorators for per-worktree scope

    Single-method protocol validated in Task 1.1.
    """

    def gather(self, project_root: Path) -> ProvisionResult:
        """Ensure source files are ready and return what was prepared.

        The returned files are DISCOVERABLE — the agent may find and read
        them via its own tools. There is no guarantee that any specific
        file will appear in the agent's prompt.

        Args:
            project_root: The project directory (main root or worktree).

        Returns:
            ProvisionResult with discovered files and capability metadata.
        """
        ...


class Verifier(Protocol):
    """FL: Checks agent output against quality criteria."""

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        """Check whether the task result meets quality criteria."""
        ...


class Constraint(Protocol):
    """AC: Enforces architectural invariants.

    Constraints run PRE-dispatch (CHECK_PRE) and POST-dispatch (CHECK_POST).
    Pre-dispatch constraint results with metadata are merged and written to
    .harness/constraints.json for the backend to read (Task 1.17).

    Only Constraints produce metadata for .harness/constraints.json. Verifiers
    do NOT — they influence the NEXT epoch via StateStore, not the current
    epoch's backend configuration (Task 1.26 temporal model).
    """

    def check(self, project_root: Path) -> VerifyResult:
        """Check whether constraints are satisfied."""
        ...


class StateStore(Protocol):
    """SC: Persists and restores state across epochs."""

    def load(self, project_root: Path) -> EpochState:
        """Load externalized state at epoch start."""
        ...

    def save(self, project_root: Path, state: EpochState) -> None:
        """Persist state at epoch end."""
        ...


class EntropyDetector(Protocol):
    """EM: Detects drift, degradation, and entropy."""

    def scan(self, project_root: Path) -> list[Task]:
        """Scan for entropy issues and return remediation tasks."""
        ...


# ─── Infrastructure Protocol ───────────────────────────────────


class WorkspaceManager(Protocol):
    """Creates and manages isolated execution environments for parallel agents.

    Infrastructure protocol — NOT one of the 6 harness dimensions.
    Provides filesystem isolation so each parallel agent operates on
    its own project_root without interfering with other agents.

    Implementations:
    - GitWorktreeManager: git worktrees with sequential merge back
    - IndependentDirManager: directory copies (non-git)

    Source: Task 1.13 (parallel dispatch design), Task 5.6 (validation).
    """

    def create(self, main_root: Path, task: Task, branch_name: str) -> Path:
        """Create an isolated workspace for one agent.

        Args:
            main_root: The main project root directory.
            task: The task to be executed in this workspace.
            branch_name: Branch name for git-based managers (may be
                ignored by non-git implementations).

        Returns:
            Path to the isolated workspace — becomes the agent's project_root.
        """
        ...

    def merge(self, worktree: Path, main_root: Path) -> MergeResult:
        """Merge or publish changes from a workspace.

        CONSTRAINT: merge() MUST NOT modify main_root beyond the
        merge/push operation itself.

        Args:
            worktree: Path to the isolated workspace.
            main_root: The main project root directory.

        Returns:
            MergeResult with success status and conflict information.
        """
        ...

    def cleanup(self, worktree: Path) -> None:
        """Remove an isolated workspace after use. Idempotent."""
        ...


class AgentBackend(Protocol):
    """The opaque coding agent — the BLACK BOX.

    execute() takes ONLY project_root (Task 1.4, F5). The agent navigates
    the filesystem using its own tools. Task assignment and context files
    are already written to disk by TaskSource and ContextSource.

    SDK CONFIGURATION (Task 1.17):
    - Backend constructor owns static configuration (model, MCP servers,
      permissions, system prompt, setting_sources).
    - REQUIRED: setting_sources=["project"] must be set for filesystem-
      provisioned context (AGENTS.md, CLAUDE.md) to be loaded by the SDK.
    - Dynamic per-epoch configuration (tool restrictions, iteration limits)
      flows through .harness/constraints.json, which the backend reads
      inside execute().

    LIFECYCLE (Task 5.1):
    - MCP server lifecycle is owned by the backend constructor.
    - Per-harness infrastructure uses Python context managers.
    - Per-worktree infrastructure uses WorkspaceManager decorators.
    """

    async def execute(self, project_root: Path) -> TaskResult:
        """Execute in a fresh context. The agent navigates the environment.

        ASYNC (Task 1.15): The Claude Agents SDK is natively async.
        This call may take minutes to hours. The async contract frees
        the event loop for parallel dispatch, health checks, and other
        concurrent work.

        The backend creates a fresh SDK client per call, reading the
        latest .harness/constraints.json for dynamic configuration.
        """
        ...
