"""Shared data types for the Rigger framework.

All types used across multiple modules are defined here. Protocols
(which reference these types) are defined in _protocols.py.

Source: Strawman API v2 §2 (Task 5.2), FL Golden Harness (Task 2.11),
.harness/ Schema Specification (Task 5.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ─── Enums ────────────────────────────────────────────────────


class VerifyAction(Enum):
    """What the harness should do after verification.

    Used by VerifyResult.action to communicate routing intent:
        ACCEPT: Checks passed; proceed to next epoch.
        RETRY: Checks failed; send feedback and re-dispatch.
        BLOCK: Hard gate; cannot proceed (constraint violation).
        ESCALATE: Retry budget exhausted; notify human operator.
    """

    ACCEPT = "accept"
    RETRY = "retry"
    BLOCK = "block"
    ESCALATE = "escalate"


class Action(Enum):
    """Control signal returned by callbacks to influence loop behavior."""

    CONTINUE = "continue"
    SKIP_TASK = "skip"
    HALT = "halt"


# ─── Dataclasses ──────────────────────────────────────────────


@dataclass
class Task:
    """A unit of work for an agent to execute.

    Serialized to .harness/current_task.json by the harness loop.
    The backend reads this from disk — the harness does NOT pass it
    via function args.
    """

    id: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Observable side effects of an agent's execution.

    Constructed by AgentBackend.execute() or by the harness loop for
    error/halt scenarios. The status field is mutable — the canonical
    loop updates it after verification.
    """

    task_id: str
    status: str  # "success", "failure", "partial", "error", etc.
    artifacts: list[Path] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpochState:
    """Externalized state readable by the loop controller.

    Serialized to .harness/state.json by the harness loop.
    epoch=0 is the initial state, semantically equivalent to a missing
    state.json file.
    """

    epoch: int = 0
    completed_tasks: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvisionResult:
    """What a ContextSource prepared for the agent.

    Two field categories:
        files: Filesystem paths written or verified on disk.
        capabilities: Human-readable descriptions of non-filesystem provisions.
    """

    files: list[Path] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)


@dataclass
class MergeResult:
    """Outcome of merging/publishing worktree changes.

    Used by WorkspaceManager.merge(). Captures success status,
    merged commits, conflict information, and diagnostic metadata.
    """

    success: bool
    merged_commits: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    worktree_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyResult:
    """Outcome of verification or constraint check.

    Used by Verifier.verify() and Constraint.check(). The __post_init__
    enforces the invariant: passed=True → ACCEPT, passed=False → non-ACCEPT.
    """

    passed: bool
    action: VerifyAction = VerifyAction.ACCEPT
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce passed/action consistency invariant."""
        if self.passed and self.action != VerifyAction.ACCEPT:
            self.action = VerifyAction.ACCEPT
        elif not self.passed and self.action == VerifyAction.ACCEPT:
            self.action = VerifyAction.RETRY
