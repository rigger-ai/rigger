"""Rigger — a declarative agent harness framework.

Public API re-exports. All internal modules use a leading underscore;
import from ``rigger`` directly for the stable surface.

Usage::

    from rigger import Harness, Task, ClaudeCodeBackend
"""

from rigger._harness import Callbacks, Harness, all_tasks_done
from rigger._merge import merge_metadata
from rigger._protocols import (
    AgentBackend,
    Constraint,
    ContextSource,
    EntropyDetector,
    StateStore,
    TaskSource,
    Verifier,
    WorkspaceManager,
)
from rigger._provisioner import ContextProvisioner, CriticalSource
from rigger._types import (
    Action,
    EpochState,
    MergeResult,
    ProvisionResult,
    Task,
    TaskResult,
    VerifyAction,
    VerifyResult,
)
from rigger.backends.claude_code import ClaudeCodeBackend
from rigger.workspace import GitWorktreeManager, IndependentDirManager

__version__ = "0.0.1"

__all__ = [
    "Action",
    "AgentBackend",
    "Callbacks",
    "ClaudeCodeBackend",
    "Constraint",
    "ContextProvisioner",
    "ContextSource",
    "CriticalSource",
    "EntropyDetector",
    "EpochState",
    "GitWorktreeManager",
    "Harness",
    "IndependentDirManager",
    "MergeResult",
    "ProvisionResult",
    "StateStore",
    "Task",
    "TaskResult",
    "TaskSource",
    "Verifier",
    "VerifyAction",
    "VerifyResult",
    "WorkspaceManager",
    "all_tasks_done",
    "merge_metadata",
]
