"""Tests for the Harness class, step methods, and canonical loop."""

from __future__ import annotations

import json
from pathlib import Path

from rigger._harness import Callbacks, Harness, all_tasks_done
from rigger._schema import HARNESS_DIR
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

# ─── Mock implementations ────────────────────────────────────


class MockTaskSource:
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self._tasks = list(tasks or [])
        self.completed: list[tuple[str, TaskResult]] = []

    def pending(self, project_root: Path) -> list[Task]:
        return list(self._tasks)

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self.completed.append((task_id, result))
        self._tasks = [t for t in self._tasks if t.id != task_id]


class MockBackend:
    def __init__(self, result: TaskResult | None = None) -> None:
        self._result = result or TaskResult(task_id="t1", status="success")
        self.calls: list[Path] = []

    async def execute(self, project_root: Path) -> TaskResult:
        self.calls.append(project_root)
        return self._result


class MockContextSource:
    def __init__(self, result: ProvisionResult | None = None) -> None:
        self._result = result or ProvisionResult()
        self.calls: list[Path] = []

    def gather(self, project_root: Path) -> ProvisionResult:
        self.calls.append(project_root)
        return self._result


class MockVerifier:
    def __init__(self, result: VerifyResult | None = None) -> None:
        self._result = result or VerifyResult(passed=True)
        self.calls: list[tuple[Path, TaskResult]] = []

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        self.calls.append((project_root, result))
        return self._result


class MockConstraint:
    def __init__(self, result: VerifyResult | None = None) -> None:
        self._result = result or VerifyResult(passed=True)
        self.calls: list[Path] = []

    def check(self, project_root: Path) -> VerifyResult:
        self.calls.append(project_root)
        return self._result


class MockStateStore:
    def __init__(self, state: EpochState | None = None) -> None:
        self._state = state or EpochState()
        self.loads: list[Path] = []
        self.saves: list[tuple[Path, EpochState]] = []

    def load(self, project_root: Path) -> EpochState:
        self.loads.append(project_root)
        return self._state

    def save(self, project_root: Path, state: EpochState) -> None:
        self.saves.append((project_root, state))


class MockEntropyDetector:
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self._tasks = tasks or []
        self.calls: list[Path] = []

    def scan(self, project_root: Path) -> list[Task]:
        self.calls.append(project_root)
        return list(self._tasks)


class MockWorkspaceManager:
    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.created: list[tuple[Path, str, str]] = []
        self.merged: list[tuple[Path, Path]] = []
        self.cleaned: list[Path] = []
        self._fail_on = fail_on or set()

    def create(self, main_root: Path, task: Task, branch_name: str) -> Path:
        if task.id in self._fail_on:
            msg = f"workspace creation failed for {task.id}"
            raise RuntimeError(msg)
        wt = main_root / ".worktrees" / task.id
        wt.mkdir(parents=True, exist_ok=True)
        self.created.append((main_root, task.id, branch_name))
        return wt

    def merge(self, worktree: Path, main_root: Path) -> MergeResult:
        self.merged.append((worktree, main_root))
        return MergeResult(success=True, merged_commits=["abc123"])

    def cleanup(self, worktree: Path) -> None:
        self.cleaned.append(worktree)


def _task(id: str = "t1", desc: str = "do stuff") -> Task:
    return Task(id=id, description=desc)


def _harness(
    tmp_path: Path,
    tasks: list[Task] | None = None,
    backend: MockBackend | None = None,
    **kwargs,
) -> Harness:
    return Harness(
        project_root=tmp_path,
        backend=backend or MockBackend(),
        task_source=MockTaskSource(tasks if tasks is not None else [_task()]),
        **kwargs,
    )


# ─── all_tasks_done ──────────────────────────────────────────


class TestAllTasksDone:
    def test_no_pending(self):
        assert all_tasks_done(EpochState(pending_tasks=[])) is True

    def test_has_pending(self):
        assert all_tasks_done(EpochState(pending_tasks=["t1"])) is False


# ─── Construction ────────────────────────────────────────────


class TestConstruction:
    def test_minimal_params(self, tmp_path):
        h = _harness(tmp_path, tasks=[])
        assert h.project_root == tmp_path
        assert h.verifiers == []
        assert h.constraints == []
        assert h.state_store is None
        assert h.entropy_detectors == []

    def test_full_params(self, tmp_path):
        cs = MockContextSource()
        v = MockVerifier()
        c = MockConstraint()
        ss = MockStateStore()
        ed = MockEntropyDetector()
        h = _harness(
            tmp_path,
            context_sources=[cs],
            verifiers=[v],
            constraints=[c],
            state_store=ss,
            entropy_detectors=[ed],
        )
        assert h.verifiers == [v]
        assert h.constraints == [c]
        assert h.state_store is ss
        assert h.entropy_detectors == [ed]

    def test_lists_are_copies(self, tmp_path):
        verifiers = [MockVerifier()]
        h = _harness(tmp_path, verifiers=verifiers)
        verifiers.append(MockVerifier())
        assert len(h.verifiers) == 1


# ─── Step methods ────────────────────────────────────────────


class TestLoadState:
    def test_with_state_store(self, tmp_path):
        state = EpochState(epoch=5, completed_tasks=["a"])
        ss = MockStateStore(state=state)
        h = _harness(tmp_path, state_store=ss)
        result = h.load_state()
        assert result.epoch == 5
        assert ss.loads == [tmp_path]

    def test_without_state_store_reads_file(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        (harness_dir / "state.json").write_text(
            json.dumps(
                {
                    "_schema_version": "1.0",
                    "epoch": 3,
                    "completed_tasks": ["x"],
                    "pending_tasks": ["y"],
                    "metadata": {},
                }
            )
        )
        h = _harness(tmp_path)
        result = h.load_state()
        assert result.epoch == 3
        assert result.completed_tasks == ["x"]

    def test_without_state_store_no_file(self, tmp_path):
        h = _harness(tmp_path)
        result = h.load_state()
        assert result.epoch == 0


class TestSelectTasks:
    def test_returns_sliced(self, tmp_path):
        tasks = [_task("t1"), _task("t2"), _task("t3")]
        h = _harness(tmp_path, tasks=tasks)
        assert len(h.select_tasks(max_count=2)) == 2
        assert h.select_tasks(max_count=2)[0].id == "t1"

    def test_default_max_count(self, tmp_path):
        tasks = [_task("t1"), _task("t2")]
        h = _harness(tmp_path, tasks=tasks)
        assert len(h.select_tasks()) == 1

    def test_empty(self, tmp_path):
        h = _harness(tmp_path, tasks=[])
        assert h.select_tasks() == []


class TestProvision:
    def test_delegates_to_provisioner(self, tmp_path):
        cs = MockContextSource(ProvisionResult(capabilities=["cap1"]))
        h = _harness(tmp_path, context_sources=[cs])
        result = h.provision()
        assert result.capabilities == ["cap1"]
        assert cs.calls == [tmp_path]

    def test_no_sources(self, tmp_path):
        h = _harness(tmp_path)
        result = h.provision()
        assert result.files == []
        assert result.capabilities == []


class TestAssignTask:
    def test_writes_current_task(self, tmp_path):
        h = _harness(tmp_path)
        h.assign_task(_task("t1", "desc1"))
        path = tmp_path / HARNESS_DIR / "current_task.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["id"] == "t1"
        assert data["description"] == "desc1"


class TestCheckConstraints:
    def test_calls_all_constraints(self, tmp_path):
        c1 = MockConstraint(VerifyResult(passed=True))
        c2 = MockConstraint(VerifyResult(passed=False, action=VerifyAction.BLOCK))
        h = _harness(tmp_path, constraints=[c1, c2])
        results = h.check_constraints()
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    def test_no_constraints(self, tmp_path):
        h = _harness(tmp_path)
        assert h.check_constraints() == []


class TestDispatch:
    async def test_assigns_and_executes(self, tmp_path):
        backend = MockBackend(TaskResult(task_id="t1", status="success"))
        h = _harness(tmp_path, backend=backend)
        result = await h.dispatch(_task("t1"))
        assert result.status == "success"
        assert backend.calls == [tmp_path]
        # current_task.json should exist
        assert (tmp_path / HARNESS_DIR / "current_task.json").exists()


class TestVerify:
    def test_calls_all_verifiers(self, tmp_path):
        v1 = MockVerifier(VerifyResult(passed=True))
        v2 = MockVerifier(VerifyResult(passed=False, action=VerifyAction.RETRY))
        h = _harness(tmp_path, verifiers=[v1, v2])
        tr = TaskResult(task_id="t1", status="success")
        results = h.verify(tr)
        assert len(results) == 2
        assert v1.calls[0][1] is tr
        assert v2.calls[0][1] is tr

    def test_no_verifiers(self, tmp_path):
        h = _harness(tmp_path)
        assert h.verify(TaskResult(task_id="t1", status="success")) == []


class TestPersist:
    def test_writes_state_file(self, tmp_path):
        h = _harness(tmp_path)
        state = EpochState(epoch=2, completed_tasks=["t1"])
        h.persist(state)
        path = tmp_path / HARNESS_DIR / "state.json"
        data = json.loads(path.read_text())
        assert data["epoch"] == 2
        assert data["completed_tasks"] == ["t1"]

    def test_calls_state_store_save(self, tmp_path):
        ss = MockStateStore()
        h = _harness(tmp_path, state_store=ss)
        state = EpochState(epoch=1)
        h.persist(state)
        assert len(ss.saves) == 1
        assert ss.saves[0][1] is state

    def test_no_state_store(self, tmp_path):
        h = _harness(tmp_path)
        h.persist(EpochState(epoch=1))
        assert (tmp_path / HARNESS_DIR / "state.json").exists()


class TestScanEntropy:
    def test_flattens_results(self, tmp_path):
        ed1 = MockEntropyDetector(tasks=[_task("e1")])
        ed2 = MockEntropyDetector(tasks=[_task("e2"), _task("e3")])
        h = _harness(tmp_path, entropy_detectors=[ed1, ed2])
        result = h.scan_entropy()
        assert [t.id for t in result] == ["e1", "e2", "e3"]

    def test_no_detectors(self, tmp_path):
        h = _harness(tmp_path)
        assert h.scan_entropy() == []


class TestWriteConstraintConfig:
    def test_writes_merged_metadata(self, tmp_path):
        h = _harness(tmp_path)
        results = [
            VerifyResult(passed=True, metadata={"allowed_tools": ["bash", "read"]}),
            VerifyResult(passed=True, metadata={"allowed_tools": ["bash", "write"]}),
        ]
        h._write_constraint_config(results)
        path = tmp_path / HARNESS_DIR / "constraints.json"
        data = json.loads(path.read_text())
        assert data["allowed_tools"] == ["bash"]

    def test_empty_metadata_deletes_file(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        constraints_path = harness_dir / "constraints.json"
        constraints_path.write_text("{}")
        h = _harness(tmp_path)
        h._write_constraint_config([VerifyResult(passed=True)])
        assert not constraints_path.exists()


# ─── run() happy path ────────────────────────────────────────


class TestRunHappyPath:
    async def test_single_epoch(self, tmp_path):
        backend = MockBackend(TaskResult(task_id="t1", status="success"))
        ts = MockTaskSource([_task("t1")])
        h = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=ts,
        )
        state = await h.run(max_epochs=1)
        assert "t1" in state.completed_tasks
        assert backend.calls == [tmp_path]
        assert len(ts.completed) == 1

    async def test_step_ordering(self, tmp_path):
        """Verify steps execute in canonical order."""
        order = []

        class TrackingTaskSource:
            def pending(self, root):
                order.append("select")
                return [_task("t1")]

            def mark_complete(self, tid, result):
                order.append("mark_complete")

        class TrackingBackend:
            async def execute(self, root):
                order.append("dispatch")
                return TaskResult(task_id="t1", status="success")

        class TrackingContextSource:
            def gather(self, root):
                order.append("provision")
                return ProvisionResult()

        class TrackingVerifier:
            def verify(self, root, result):
                order.append("verify")
                return VerifyResult(passed=True)

        h = Harness(
            project_root=tmp_path,
            backend=TrackingBackend(),
            task_source=TrackingTaskSource(),
            context_sources=[TrackingContextSource()],
            verifiers=[TrackingVerifier()],
        )
        await h.run(max_epochs=1)
        # select(load_state reads file, not pending), select(select_tasks),
        # provision, dispatch, verify, mark_complete,
        # select(stop_when refresh of pending_tasks)
        expected = [
            "select",
            "provision",
            "dispatch",
            "verify",
            "mark_complete",
            "select",
        ]
        assert order == expected

    async def test_multiple_epochs(self, tmp_path):
        tasks = [_task("t1"), _task("t2")]
        backend = MockBackend(TaskResult(task_id="", status="success"))
        ts = MockTaskSource(tasks)
        h = Harness(project_root=tmp_path, backend=backend, task_source=ts)
        await h.run(max_epochs=3, stop_when=lambda s: False)
        assert len(ts.completed) == 2


# ─── run() stop conditions ───────────────────────────────────


class TestRunStopConditions:
    async def test_no_tasks_breaks(self, tmp_path):
        h = _harness(tmp_path, tasks=[])
        state = await h.run(max_epochs=5)
        assert state.completed_tasks == []

    async def test_max_epochs_respected(self, tmp_path):
        """Tasks keep returning but max_epochs limits execution."""

        class InfiniteTaskSource:
            def __init__(self):
                self.epoch_count = 0

            def pending(self, root):
                return [_task(f"t{self.epoch_count}")]

            def mark_complete(self, tid, result):
                self.epoch_count += 1

        ts = InfiniteTaskSource()
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=ts,
        )
        await h.run(max_epochs=3, stop_when=lambda s: False)
        assert ts.epoch_count == 3

    async def test_stop_when_predicate(self, tmp_path):
        tasks = [_task("t1"), _task("t2"), _task("t3")]
        ts = MockTaskSource(tasks)
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=ts,
        )
        await h.run(
            max_epochs=10,
            stop_when=lambda s: len(s.completed_tasks) >= 1,
        )
        assert len(ts.completed) == 1


# ─── run() callbacks ─────────────────────────────────────────


class TestRunCallbacks:
    async def test_epoch_start_halt(self, tmp_path):
        h = _harness(tmp_path)
        cb = Callbacks(on_epoch_start=lambda e, s: Action.HALT)
        state = await h.run(callbacks=cb)
        assert state.completed_tasks == []

    async def test_task_selected_halt(self, tmp_path):
        h = _harness(tmp_path)
        cb = Callbacks(on_task_selected=lambda t: Action.HALT)
        state = await h.run(callbacks=cb)
        assert state.completed_tasks == []

    async def test_task_selected_skip(self, tmp_path):
        call_count = 0

        def on_select(task):
            nonlocal call_count
            call_count += 1
            return Action.SKIP_TASK if call_count == 1 else None

        tasks = [_task("t1"), _task("t2")]
        h = _harness(tmp_path, tasks=tasks)
        cb = Callbacks(on_task_selected=on_select)
        state = await h.run(max_epochs=2, callbacks=cb, stop_when=lambda s: False)
        # First epoch skipped, second executed t1
        assert len(state.completed_tasks) >= 1

    async def test_provision_halt(self, tmp_path):
        h = _harness(tmp_path)
        cb = Callbacks(on_provision_complete=lambda r: Action.HALT)
        state = await h.run(callbacks=cb)
        assert state.completed_tasks == []

    async def test_provision_skip(self, tmp_path):
        h = _harness(tmp_path)
        cb = Callbacks(on_provision_complete=lambda r: Action.SKIP_TASK)
        state = await h.run(max_epochs=1, callbacks=cb)
        assert state.completed_tasks == []

    async def test_task_complete_halt(self, tmp_path):
        backend = MockBackend(TaskResult(task_id="t1", status="success"))
        h = _harness(tmp_path, backend=backend)
        cb = Callbacks(on_task_complete=lambda r: Action.HALT)
        state = await h.run(callbacks=cb)
        # Dispatched but halted before verify/persist
        assert state.completed_tasks == []

    async def test_verify_complete_halt(self, tmp_path):
        h = _harness(tmp_path, verifiers=[MockVerifier()])
        cb = Callbacks(on_verify_complete=lambda r, vrs: Action.HALT)
        state = await h.run(callbacks=cb)
        # Verified but halted before persist
        assert state.completed_tasks == []

    async def test_epoch_end_halt(self, tmp_path):
        tasks = [_task("t1"), _task("t2")]
        h = _harness(tmp_path, tasks=tasks)
        cb = Callbacks(on_epoch_end=lambda e, s: Action.HALT)
        state = await h.run(max_epochs=5, callbacks=cb, stop_when=lambda s: False)
        # Only one epoch completes
        assert len(state.completed_tasks) == 1

    async def test_entropy_scan_halt(self, tmp_path):
        tasks = [_task("t1"), _task("t2")]
        ed = MockEntropyDetector(tasks=[_task("e1")])
        h = _harness(tmp_path, tasks=tasks, entropy_detectors=[ed])
        cb = Callbacks(on_entropy_scan=lambda ts: Action.HALT)
        state = await h.run(max_epochs=5, callbacks=cb, stop_when=lambda s: False)
        assert len(state.completed_tasks) == 1


# ─── run() constraint gate ───────────────────────────────────


class TestRunConstraintGate:
    async def test_pre_constraint_failure_skips_epoch(self, tmp_path):
        constraint = MockConstraint(
            VerifyResult(passed=False, action=VerifyAction.BLOCK, message="blocked")
        )
        backend = MockBackend()
        h = _harness(tmp_path, backend=backend, constraints=[constraint])
        state = await h.run(max_epochs=1)
        # Backend never called
        assert backend.calls == []
        assert state.completed_tasks == []

    async def test_mixed_constraints_one_fails(self, tmp_path):
        c_pass = MockConstraint(VerifyResult(passed=True))
        c_fail = MockConstraint(VerifyResult(passed=False, action=VerifyAction.BLOCK))
        backend = MockBackend()
        h = _harness(tmp_path, backend=backend, constraints=[c_pass, c_fail])
        await h.run(max_epochs=1)
        assert backend.calls == []


# ─── run() verification ──────────────────────────────────────


class TestRunVerification:
    async def test_all_pass_sets_verified(self, tmp_path):
        ts = MockTaskSource([_task("t1")])
        v = MockVerifier(VerifyResult(passed=True))
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=ts,
            verifiers=[v],
        )
        await h.run(max_epochs=1)
        assert ts.completed[0][1].status == "verified"

    async def test_any_fail_sets_verification_failed(self, tmp_path):
        ts = MockTaskSource([_task("t1")])
        v_pass = MockVerifier(VerifyResult(passed=True))
        v_fail = MockVerifier(VerifyResult(passed=False, action=VerifyAction.RETRY))
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=ts,
            verifiers=[v_pass, v_fail],
        )
        await h.run(max_epochs=1)
        assert ts.completed[0][1].status == "verification_failed"

    async def test_no_verifiers_preserves_status(self, tmp_path):
        ts = MockTaskSource([_task("t1")])
        backend = MockBackend(TaskResult(task_id="t1", status="success"))
        h = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=ts,
        )
        await h.run(max_epochs=1)
        assert ts.completed[0][1].status == "success"


# ─── run_once() ──────────────────────────────────────────────


class TestRunOnce:
    async def test_happy_path(self, tmp_path):
        backend = MockBackend(TaskResult(task_id="t1", status="success"))
        h = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=MockTaskSource(),
        )
        result = await h.run_once(_task("t1"))
        assert result.status == "success"
        assert backend.calls == [tmp_path]

    async def test_constraint_violation(self, tmp_path):
        constraint = MockConstraint(
            VerifyResult(passed=False, action=VerifyAction.BLOCK)
        )
        backend = MockBackend()
        h = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=MockTaskSource(),
            constraints=[constraint],
        )
        result = await h.run_once(_task("t1"))
        assert result.status == "constraint_violation"
        assert backend.calls == []

    async def test_halted_on_provision(self, tmp_path):
        backend = MockBackend()
        h = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=MockTaskSource(),
        )
        cb = Callbacks(on_provision_complete=lambda r: Action.HALT)
        result = await h.run_once(_task("t1"), callbacks=cb)
        assert result.status == "halted"
        assert backend.calls == []

    async def test_verification_applied(self, tmp_path):
        v = MockVerifier(VerifyResult(passed=True))
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=MockTaskSource(),
            verifiers=[v],
        )
        result = await h.run_once(_task("t1"))
        assert result.status == "verified"

    async def test_no_persist_called(self, tmp_path):
        """run_once does not call persist — no state.json written."""
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=MockTaskSource(),
        )
        await h.run_once(_task("t1"))
        assert not (tmp_path / HARNESS_DIR / "state.json").exists()


# ─── run_sync() ──────────────────────────────────────────────


class TestRunSync:
    def test_delegates_correctly(self, tmp_path):
        ts = MockTaskSource([_task("t1")])
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=ts,
        )
        state = h.run_sync(max_epochs=1)
        assert "t1" in state.completed_tasks


# ─── Write order ─────────────────────────────────────────────


class TestWriteOrder:
    async def test_current_task_written_before_execute(self, tmp_path):
        """current_task.json exists when backend.execute() is called."""
        task_file_existed = []

        class CheckingBackend:
            async def execute(self, root):
                exists = (root / HARNESS_DIR / "current_task.json").exists()
                task_file_existed.append(exists)
                return TaskResult(task_id="t1", status="success")

        h = Harness(
            project_root=tmp_path,
            backend=CheckingBackend(),
            task_source=MockTaskSource([_task("t1")]),
        )
        await h.run(max_epochs=1)
        assert task_file_existed == [True]

    async def test_state_written_after_dispatch(self, tmp_path):
        """state.json is written during persist, after dispatch."""
        h = _harness(tmp_path)
        await h.run(max_epochs=1)
        path = tmp_path / HARNESS_DIR / "state.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "t1" in data["completed_tasks"]


# ─── dispatch_parallel() ─────────────────────────────────


class TestDispatchParallel:
    async def test_parallel_creates_workspaces(self, tmp_path):
        """N tasks → N workspace creates."""
        wm = MockWorkspaceManager()
        backend = MockBackend(TaskResult(task_id="", status="success"))
        h = Harness(
            project_root=tmp_path,
            backend=backend,
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        batch = [_task("t1"), _task("t2"), _task("t3")]
        results, halt = await h.dispatch_parallel(batch, EpochState(epoch=1))
        assert len(wm.created) == 3
        assert len(results) == 3
        assert not halt

    async def test_parallel_gather_semantics(self, tmp_path):
        """All results collected even on partial failure."""
        call_count = 0

        class PartialBackend:
            async def execute(self, project_root):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("agent 2 failed")
                return TaskResult(task_id="ok", status="success")

        wm = MockWorkspaceManager()
        h = Harness(
            project_root=tmp_path,
            backend=PartialBackend(),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        batch = [_task("t1"), _task("t2"), _task("t3")]
        results, _ = await h.dispatch_parallel(batch, EpochState(epoch=1))
        assert len(results) == 3
        statuses = [r.status for r in results]
        assert statuses.count("error") == 1
        assert statuses.count("success") == 2

    async def test_parallel_halt_flag(self, tmp_path):
        """Callback HALT sets flag but batch completes."""
        wm = MockWorkspaceManager()
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(TaskResult(task_id="", status="success")),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        cb = Callbacks(on_task_complete=lambda r: Action.HALT)
        batch = [_task("t1"), _task("t2")]
        results, halt = await h.dispatch_parallel(
            batch, EpochState(epoch=1), callbacks=cb
        )
        assert halt is True
        assert len(results) == 2

    async def test_parallel_cleanup_always_runs(self, tmp_path):
        """Cleanup called even on errors."""

        class FailingBackend:
            async def execute(self, project_root):
                raise RuntimeError("boom")

        wm = MockWorkspaceManager()
        h = Harness(
            project_root=tmp_path,
            backend=FailingBackend(),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        batch = [_task("t1"), _task("t2")]
        results, _ = await h.dispatch_parallel(batch, EpochState(epoch=1))
        assert len(wm.cleaned) == 2
        assert all(r.status == "error" for r in results)

    async def test_parallel_merge_sequential(self, tmp_path):
        """Merge called in order for successful results."""
        wm = MockWorkspaceManager()
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(TaskResult(task_id="", status="success")),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        batch = [_task("t1"), _task("t2"), _task("t3")]
        await h.dispatch_parallel(batch, EpochState(epoch=1))
        assert len(wm.merged) == 3
        # Verify merge order matches task order
        for _wt_path, main_root in wm.merged:
            assert main_root == tmp_path

    async def test_parallel_error_result_on_creation_failure(self, tmp_path):
        """Failed worktree → error TaskResult, others continue."""
        wm = MockWorkspaceManager(fail_on={"t2"})
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(TaskResult(task_id="", status="success")),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        batch = [_task("t1"), _task("t2"), _task("t3")]
        results, _ = await h.dispatch_parallel(batch, EpochState(epoch=1))
        assert len(results) == 3
        assert results[0].status == "success"
        assert results[1].status == "error"
        assert results[2].status == "success"

    async def test_parallel_all_creations_fail(self, tmp_path):
        """All creation failures → error results immediately."""
        wm = MockWorkspaceManager(fail_on={"t1", "t2"})
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        batch = [_task("t1"), _task("t2")]
        results, halt = await h.dispatch_parallel(batch, EpochState(epoch=1))
        assert len(results) == 2
        assert all(r.status == "error" for r in results)
        assert not halt

    async def test_parallel_requires_workspace_manager(self, tmp_path):
        """dispatch_parallel raises without workspace_manager."""
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(),
            task_source=MockTaskSource(),
        )
        import pytest

        with pytest.raises(RuntimeError, match="workspace_manager"):
            await h.dispatch_parallel([_task("t1")], EpochState())

    async def test_parallel_copies_provisioned_content(self, tmp_path):
        """Provisioned files are copied to each worktree."""
        # Create a provisioned file
        src_file = tmp_path / "context" / "guide.md"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("context data")

        wm = MockWorkspaceManager()
        h = Harness(
            project_root=tmp_path,
            backend=MockBackend(TaskResult(task_id="", status="success")),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        provision = ProvisionResult(files=[src_file])
        batch = [_task("t1")]
        await h.dispatch_parallel(
            batch, EpochState(epoch=1), provision_results=[provision]
        )
        # Check file was copied to worktree
        wt = tmp_path / ".worktrees" / "t1"
        copied = wt / "context" / "guide.md"
        assert copied.exists()
        assert copied.read_text() == "context data"

    async def test_parallel_writes_harness_files(self, tmp_path):
        """Each worktree gets current_task.json and state.json."""
        task_files_seen = []

        class CheckingBackend:
            async def execute(self, project_root):
                ct = (project_root / HARNESS_DIR / "current_task.json").exists()
                st = (project_root / HARNESS_DIR / "state.json").exists()
                task_files_seen.append((ct, st))
                return TaskResult(task_id="t1", status="success")

        wm = MockWorkspaceManager()
        h = Harness(
            project_root=tmp_path,
            backend=CheckingBackend(),
            task_source=MockTaskSource(),
            workspace_manager=wm,
        )
        await h.dispatch_parallel([_task("t1")], EpochState(epoch=1))
        assert task_files_seen == [(True, True)]
