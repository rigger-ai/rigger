"""Public API surface tests and end-to-end smoke test."""

from __future__ import annotations

from pathlib import Path

import rigger
from rigger import (  # noqa: F401
    Action,
    AgentBackend,
    Callbacks,
    ClaudeCodeBackend,
    Constraint,
    ContextProvisioner,
    ContextSource,
    CriticalSource,
    EntropyDetector,
    EpochState,
    GitWorktreeManager,
    Harness,
    IndependentDirManager,
    MergeResult,
    ProvisionResult,
    StateStore,
    Task,
    TaskResult,
    TaskSource,
    Verifier,
    VerifyAction,
    VerifyResult,
    WorkspaceManager,
    all_tasks_done,
    merge_metadata,
)

# ─── __all__ completeness ────────────────────────────────────


class TestAll:
    def test_all_matches_exports(self):
        """__all__ contains exactly the names we import above."""
        expected = {
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
        }
        assert set(rigger.__all__) == expected

    def test_no_extra_public_names(self):
        """__all__ covers every non-dunder, non-private name on the module."""
        public = {
            name
            for name in dir(rigger)
            if not name.startswith("_") and name != "__version__"
        }
        # Remove submodule names that appear on the package
        submodules = {"backends", "workspace"}
        public -= submodules
        assert public == set(rigger.__all__)

    def test_version_present(self):
        assert hasattr(rigger, "__version__")
        assert isinstance(rigger.__version__, str)


# ─── Import paths ────────────────────────────────────────────


class TestImportPaths:
    """Verify the canonical import spelled out in the task spec."""

    def test_from_rigger_import_harness(self):
        assert Harness is not None

    def test_from_rigger_import_task(self):
        assert Task is not None

    def test_from_rigger_import_context_source(self):
        assert ContextSource is not None

    def test_from_rigger_import_claude_code_backend(self):
        assert ClaudeCodeBackend is not None


# ─── Smoke test: single-epoch end-to-end ─────────────────────


class _StubTaskSource:
    """Minimal TaskSource that yields one task then reports empty."""

    def __init__(self) -> None:
        self._tasks = [Task(id="smoke-1", description="smoke test task")]
        self.completed: list[str] = []

    def pending(self, project_root: Path) -> list[Task]:
        return list(self._tasks)

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self.completed.append(task_id)
        self._tasks = [t for t in self._tasks if t.id != task_id]


class _StubBackend:
    """Minimal AgentBackend returning success."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    async def execute(self, project_root: Path) -> TaskResult:
        self.calls.append(project_root)
        return TaskResult(task_id="smoke-1", status="success")


class _StubContextSource:
    """Minimal ContextSource."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def gather(self, project_root: Path) -> ProvisionResult:
        self.calls.append(project_root)
        return ProvisionResult(capabilities=["stub context"])


class _StubVerifier:
    """Minimal Verifier that always passes."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, TaskResult]] = []

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        self.calls.append((project_root, result))
        return VerifyResult(passed=True)


class _StubConstraint:
    """Minimal Constraint that always passes."""

    def check(self, project_root: Path) -> VerifyResult:
        return VerifyResult(passed=True, metadata={"allowed_tools": ["bash"]})


class _StubStateStore:
    """Minimal StateStore."""

    def __init__(self) -> None:
        self._state = EpochState()
        self.saves: list[EpochState] = []

    def load(self, project_root: Path) -> EpochState:
        return self._state

    def save(self, project_root: Path, state: EpochState) -> None:
        self.saves.append(state)
        self._state = state


class _StubEntropyDetector:
    """Minimal EntropyDetector that finds nothing."""

    def scan(self, project_root: Path) -> list[Task]:
        return []


class TestSmokeEndToEnd:
    """Construct a Harness with all dimension mocks and run one epoch."""

    async def test_single_epoch_all_steps(self, tmp_path):
        ts = _StubTaskSource()
        backend = _StubBackend()
        ctx = _StubContextSource()
        verifier = _StubVerifier()
        constraint = _StubConstraint()
        state_store = _StubStateStore()
        entropy = _StubEntropyDetector()

        # Track step ordering via callbacks
        steps: list[str] = []
        callbacks = Callbacks(
            on_epoch_start=lambda e, s: steps.append("epoch_start"),
            on_task_selected=lambda t: steps.append("task_selected"),
            on_provision_complete=lambda r: steps.append("provision_complete"),
            on_task_complete=lambda r: steps.append("task_complete"),
            on_verify_complete=lambda r, vrs: steps.append("verify_complete"),
            on_epoch_end=lambda e, s: steps.append("epoch_end"),
            on_entropy_scan=lambda ts: steps.append("entropy_scan"),
        )

        harness = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=ts,
            context_sources=[ctx],
            verifiers=[verifier],
            constraints=[constraint],
            state_store=state_store,
            entropy_detectors=[entropy],
        )

        final_state = await harness.run(
            max_epochs=1,
            stop_when=all_tasks_done,
            callbacks=callbacks,
        )

        # Backend was called exactly once
        assert len(backend.calls) == 1
        assert backend.calls[0] == tmp_path

        # Context source was provisioned
        assert len(ctx.calls) == 1

        # Verifier was called
        assert len(verifier.calls) == 1

        # Task was completed
        assert ts.completed == ["smoke-1"]
        assert "smoke-1" in final_state.completed_tasks

        # State was persisted
        assert len(state_store.saves) == 1

        # All callbacks fired in canonical order
        assert steps == [
            "epoch_start",
            "task_selected",
            "provision_complete",
            "task_complete",
            "verify_complete",
            "epoch_end",
            "entropy_scan",
        ]

    def test_run_sync_equivalent(self, tmp_path):
        """run_sync() produces the same result as await run()."""
        ts = _StubTaskSource()
        backend = _StubBackend()

        harness = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=ts,
        )

        state = harness.run_sync(max_epochs=1, stop_when=all_tasks_done)
        assert "smoke-1" in state.completed_tasks

    async def test_run_once_smoke(self, tmp_path):
        """run_once() dispatches a single task without persist."""
        backend = _StubBackend()
        verifier = _StubVerifier()

        harness = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=_StubTaskSource(),
            verifiers=[verifier],
        )

        task = Task(id="once-1", description="one-shot task")
        result = await harness.run_once(task)
        assert result.status == "verified"
        assert len(backend.calls) == 1

    async def test_critical_source_integration(self, tmp_path):
        """CriticalSource wraps a ContextSource for fail-stop behavior."""
        inner = _StubContextSource()
        critical = CriticalSource(inner)

        result = critical.gather(tmp_path)
        assert result.capabilities == ["stub context"]
        assert len(inner.calls) == 1

    async def test_context_provisioner_integration(self, tmp_path):
        """ContextProvisioner aggregates multiple sources."""
        s1 = _StubContextSource()
        s2 = _StubContextSource()
        provisioner = ContextProvisioner(sources=[s1, s2])

        result = provisioner.provision(tmp_path)
        assert result.capabilities == ["stub context", "stub context"]

    def test_merge_metadata_integration(self):
        """merge_metadata combines constraint results."""
        results = [
            VerifyResult(passed=True, metadata={"allowed_tools": ["bash", "read"]}),
            VerifyResult(passed=True, metadata={"allowed_tools": ["bash", "write"]}),
        ]
        merged = merge_metadata(results)
        assert merged["allowed_tools"] == ["bash"]
