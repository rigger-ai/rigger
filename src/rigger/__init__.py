"""Rigger — a declarative agent harness framework.

Public API re-exports. All internal modules use a leading underscore;
import from ``rigger`` directly for the stable surface.

Usage::

    from rigger import Harness, Task, ClaudeCodeBackend
"""

from rigger._config import (
    ComponentConfig,
    HarnessConfig,
    RunConfig,
    build_harness,
    get_stop_predicate,
    load_config,
)
from rigger._harness import Callbacks, Harness, all_tasks_done
from rigger._lock import (
    HarnessAlreadyRunning,
    LockInfo,
    acquire_lock,
    harness_lock,
    release_lock,
)
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
from rigger._registry import Registry, registry
from rigger._schema import FilesystemEntropyTaskSource, write_entropy_tasks
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
from rigger.constraints import (
    BranchPolicyConstraint,
    ToolAllowlistConstraint,
)
from rigger.context_sources import (
    AgentsMdContextSource,
    FileTreeContextSource,
    McpCapabilityContextSource,
    StaticFilesContextSource,
)
from rigger.entropy_detectors import (
    DocStalenessEntropyDetector,
    ShellCommandEntropyDetector,
)
from rigger.state_stores import (
    HarnessDirStateStore,
    JsonFileStateStore,
)
from rigger.task_sources import (
    AtomicIssueTaskSource,
    FileListTaskSource,
    JsonStoriesTaskSource,
    LinearTaskSource,
)
from rigger.verifiers import (
    CiStatusVerifier,
    LintVerifier,
    RatchetVerifier,
    TestSuiteVerifier,
)
from rigger.workspace import (
    GitWorktreeManager,
    IndependentBranchManager,
    IndependentDirManager,
)

__version__ = "0.0.1"

__all__ = [
    "Action",
    "AgentBackend",
    "AgentsMdContextSource",
    "AtomicIssueTaskSource",
    "BranchPolicyConstraint",
    "Callbacks",
    "CiStatusVerifier",
    "ClaudeCodeBackend",
    "ComponentConfig",
    "Constraint",
    "ContextProvisioner",
    "ContextSource",
    "CriticalSource",
    "DocStalenessEntropyDetector",
    "EntropyDetector",
    "EpochState",
    "FileListTaskSource",
    "FileTreeContextSource",
    "FilesystemEntropyTaskSource",
    "GitWorktreeManager",
    "Harness",
    "HarnessAlreadyRunning",
    "HarnessConfig",
    "HarnessDirStateStore",
    "IndependentBranchManager",
    "IndependentDirManager",
    "JsonFileStateStore",
    "JsonStoriesTaskSource",
    "LinearTaskSource",
    "LintVerifier",
    "LockInfo",
    "McpCapabilityContextSource",
    "MergeResult",
    "ProvisionResult",
    "RatchetVerifier",
    "Registry",
    "RunConfig",
    "ShellCommandEntropyDetector",
    "StateStore",
    "StaticFilesContextSource",
    "Task",
    "TaskResult",
    "TaskSource",
    "TestSuiteVerifier",
    "ToolAllowlistConstraint",
    "Verifier",
    "VerifyAction",
    "VerifyResult",
    "WorkspaceManager",
    "acquire_lock",
    "all_tasks_done",
    "build_harness",
    "get_stop_predicate",
    "harness_lock",
    "load_config",
    "merge_metadata",
    "registry",
    "release_lock",
    "write_entropy_tasks",
]
