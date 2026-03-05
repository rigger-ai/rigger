"""Tests for rigger._protocols — structural subtyping verification.

Each test creates a concrete class that satisfies a protocol and verifies
it is accepted by isinstance() checks (via @runtime_checkable) or by
direct usage in typed contexts.
"""

from pathlib import Path

from rigger._protocols import (
    AgentBackend,
    Constraint,
    ContextSource,
    EntropyDetector,
    StateStore,
    TaskSource,
    Verifier,
)
from rigger._types import (
    EpochState,
    ProvisionResult,
    Task,
    TaskResult,
    VerifyResult,
)

# ─── TaskSource ──────────────────────────────────────────────────


class ConcreteTaskSource:
    """Minimal implementation satisfying the TaskSource protocol."""

    def __init__(self):
        self._tasks = [Task(id="t1", description="Do something")]
        self._completed: list[str] = []

    def pending(self, project_root: Path) -> list[Task]:
        return [t for t in self._tasks if t.id not in self._completed]

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self._completed.append(task_id)


class TestTaskSource:
    def test_structural_subtyping(self):
        source: TaskSource = ConcreteTaskSource()
        tasks = source.pending(Path("/fake/project"))
        assert len(tasks) == 1
        assert tasks[0].id == "t1"

    def test_mark_complete(self):
        source: TaskSource = ConcreteTaskSource()
        source.mark_complete("t1", TaskResult(task_id="t1", status="success"))
        assert source.pending(Path("/fake/project")) == []

    def test_empty_pending(self):
        source: TaskSource = ConcreteTaskSource()
        source.mark_complete("t1", TaskResult(task_id="t1", status="success"))
        result = source.pending(Path("/fake/project"))
        assert result == []


# ─── ContextSource ───────────────────────────────────────────────


class ConcreteContextSource:
    """Minimal implementation satisfying the ContextSource protocol."""

    def gather(self, project_root: Path) -> ProvisionResult:
        return ProvisionResult(
            files=[project_root / "CLAUDE.md"],
            capabilities=["project docs provided"],
        )


class TestContextSource:
    def test_structural_subtyping(self):
        source: ContextSource = ConcreteContextSource()
        result = source.gather(Path("/fake/project"))
        assert isinstance(result, ProvisionResult)
        assert len(result.files) == 1
        assert result.capabilities == ["project docs provided"]

    def test_empty_provision(self):
        class EmptySource:
            def gather(self, project_root: Path) -> ProvisionResult:
                return ProvisionResult()

        source: ContextSource = EmptySource()
        result = source.gather(Path("/fake/project"))
        assert result.files == []
        assert result.capabilities == []


# ─── Verifier ────────────────────────────────────────────────────


class ConcreteVerifier:
    """Minimal implementation satisfying the Verifier protocol."""

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        return VerifyResult(passed=result.status == "success")


class TestVerifier:
    def test_structural_subtyping_pass(self):
        verifier: Verifier = ConcreteVerifier()
        vr = verifier.verify(
            Path("/fake/project"),
            TaskResult(task_id="t1", status="success"),
        )
        assert vr.passed is True

    def test_structural_subtyping_fail(self):
        verifier: Verifier = ConcreteVerifier()
        vr = verifier.verify(
            Path("/fake/project"),
            TaskResult(task_id="t1", status="failure"),
        )
        assert vr.passed is False


# ─── Constraint ──────────────────────────────────────────────────


class ConcreteConstraint:
    """Minimal implementation satisfying the Constraint protocol."""

    def check(self, project_root: Path) -> VerifyResult:
        return VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["rm"]},
        )


class TestConstraint:
    def test_structural_subtyping(self):
        constraint: Constraint = ConcreteConstraint()
        result = constraint.check(Path("/fake/project"))
        assert result.passed is True
        assert result.metadata["disallowed_tools"] == ["rm"]


# ─── StateStore ──────────────────────────────────────────────────


class ConcreteStateStore:
    """Minimal implementation satisfying the StateStore protocol."""

    def __init__(self):
        self._state = EpochState()

    def load(self, project_root: Path) -> EpochState:
        return self._state

    def save(self, project_root: Path, state: EpochState) -> None:
        self._state = state


class TestStateStore:
    def test_structural_subtyping(self):
        store: StateStore = ConcreteStateStore()
        state = store.load(Path("/fake/project"))
        assert state.epoch == 0

    def test_round_trip(self):
        store: StateStore = ConcreteStateStore()
        new_state = EpochState(epoch=3, completed_tasks=["t1", "t2"])
        store.save(Path("/fake/project"), new_state)
        loaded = store.load(Path("/fake/project"))
        assert loaded.epoch == 3
        assert loaded.completed_tasks == ["t1", "t2"]


# ─── EntropyDetector ────────────────────────────────────────────


class ConcreteEntropyDetector:
    """Minimal implementation satisfying the EntropyDetector protocol."""

    def scan(self, project_root: Path) -> list[Task]:
        return [Task(id="entropy-1", description="Fix drift in module X")]


class TestEntropyDetector:
    def test_structural_subtyping(self):
        detector: EntropyDetector = ConcreteEntropyDetector()
        tasks = detector.scan(Path("/fake/project"))
        assert len(tasks) == 1
        assert tasks[0].id == "entropy-1"

    def test_no_entropy(self):
        class CleanDetector:
            def scan(self, project_root: Path) -> list[Task]:
                return []

        detector: EntropyDetector = CleanDetector()
        assert detector.scan(Path("/fake/project")) == []


# ─── AgentBackend ────────────────────────────────────────────────


class ConcreteBackend:
    """Minimal implementation satisfying the AgentBackend protocol."""

    async def execute(self, project_root: Path) -> TaskResult:
        return TaskResult(task_id="t1", status="success")


class TestAgentBackend:
    async def test_structural_subtyping(self):
        backend: AgentBackend = ConcreteBackend()
        result = await backend.execute(Path("/fake/project"))
        assert result.task_id == "t1"
        assert result.status == "success"

    async def test_with_artifacts(self):
        class RichBackend:
            async def execute(self, project_root: Path) -> TaskResult:
                return TaskResult(
                    task_id="t1",
                    status="partial",
                    artifacts=[project_root / "output.py"],
                    commits=["abc123"],
                    metadata={"execution_time_s": 120.0},
                )

        backend: AgentBackend = RichBackend()
        result = await backend.execute(Path("/fake/project"))
        assert result.status == "partial"
        assert len(result.artifacts) == 1
        assert result.commits == ["abc123"]


# ─── Protocol importability ─────────────────────────────────────


class TestImportability:
    """Verify all protocols are importable from rigger._protocols."""

    def test_all_protocols_importable(self):
        protocols = [
            TaskSource,
            ContextSource,
            Verifier,
            Constraint,
            StateStore,
            EntropyDetector,
            AgentBackend,
        ]
        assert len(protocols) == 7
        for proto in protocols:
            assert issubclass(proto, object)
