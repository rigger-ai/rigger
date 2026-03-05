"""Tests for rigger._types — shared data types."""

from pathlib import Path

from rigger._types import (
    Action,
    EpochState,
    ProvisionResult,
    Task,
    TaskResult,
    VerifyAction,
    VerifyResult,
)

# ─── Task ─────────────────────────────────────────────────────


class TestTask:
    def test_construction_required_fields(self):
        t = Task(id="t1", description="Do something")
        assert t.id == "t1"
        assert t.description == "Do something"
        assert t.metadata == {}

    def test_construction_with_metadata(self):
        t = Task(id="t2", description="x", metadata={"priority": 1})
        assert t.metadata == {"priority": 1}

    def test_metadata_default_is_independent(self):
        t1 = Task(id="a", description="x")
        t2 = Task(id="b", description="y")
        t1.metadata["key"] = "val"
        assert "key" not in t2.metadata


# ─── TaskResult ───────────────────────────────────────────────


class TestTaskResult:
    def test_construction_required_fields(self):
        r = TaskResult(task_id="t1", status="success")
        assert r.task_id == "t1"
        assert r.status == "success"
        assert r.artifacts == []
        assert r.commits == []
        assert r.metadata == {}

    def test_construction_all_fields(self):
        r = TaskResult(
            task_id="t1",
            status="partial",
            artifacts=[Path("a.py")],
            commits=["abc123"],
            metadata={"execution_time_s": 42.0},
        )
        assert r.artifacts == [Path("a.py")]
        assert r.commits == ["abc123"]
        assert r.metadata["execution_time_s"] == 42.0

    def test_status_is_mutable(self):
        r = TaskResult(task_id="t1", status="partial")
        r.status = "success"
        assert r.status == "success"

    def test_status_accepts_arbitrary_strings(self):
        for status in ("success", "failure", "partial", "error", "halted", "custom"):
            r = TaskResult(task_id="t1", status=status)
            assert r.status == status


# ─── EpochState ───────────────────────────────────────────────


class TestEpochState:
    def test_default_construction(self):
        s = EpochState()
        assert s.epoch == 0
        assert s.completed_tasks == []
        assert s.pending_tasks == []
        assert s.metadata == {}

    def test_construction_with_values(self):
        s = EpochState(
            epoch=3,
            completed_tasks=["t1", "t2"],
            pending_tasks=["t3"],
            metadata={"retries": 1},
        )
        assert s.epoch == 3
        assert s.completed_tasks == ["t1", "t2"]

    def test_is_mutable(self):
        s = EpochState()
        s.epoch = 5
        s.completed_tasks.append("t1")
        assert s.epoch == 5
        assert s.completed_tasks == ["t1"]


# ─── ProvisionResult ─────────────────────────────────────────


class TestProvisionResult:
    def test_default_construction(self):
        p = ProvisionResult()
        assert p.files == []
        assert p.capabilities == []

    def test_construction_with_values(self):
        p = ProvisionResult(
            files=[Path("CLAUDE.md"), Path("spec.txt")],
            capabilities=["linting config provided"],
        )
        assert len(p.files) == 2
        assert p.capabilities == ["linting config provided"]


# ─── VerifyAction ─────────────────────────────────────────────


class TestVerifyAction:
    def test_four_members(self):
        assert len(VerifyAction) == 4

    def test_values(self):
        assert VerifyAction.ACCEPT.value == "accept"
        assert VerifyAction.RETRY.value == "retry"
        assert VerifyAction.BLOCK.value == "block"
        assert VerifyAction.ESCALATE.value == "escalate"


# ─── Action ───────────────────────────────────────────────────


class TestAction:
    def test_three_members(self):
        assert len(Action) == 3

    def test_values(self):
        assert Action.CONTINUE.value == "continue"
        assert Action.SKIP_TASK.value == "skip"
        assert Action.HALT.value == "halt"


# ─── VerifyResult ─────────────────────────────────────────────


class TestVerifyResult:
    def test_passed_defaults_to_accept(self):
        r = VerifyResult(passed=True)
        assert r.action == VerifyAction.ACCEPT
        assert r.message == ""
        assert r.details == {}
        assert r.metadata == {}

    def test_failed_defaults_to_retry(self):
        """passed=False with default action=ACCEPT auto-corrects to RETRY."""
        r = VerifyResult(passed=False)
        assert r.action == VerifyAction.RETRY

    def test_failed_with_explicit_action_preserved(self):
        r = VerifyResult(passed=False, action=VerifyAction.BLOCK)
        assert r.action == VerifyAction.BLOCK

    def test_failed_escalate_preserved(self):
        r = VerifyResult(passed=False, action=VerifyAction.ESCALATE)
        assert r.action == VerifyAction.ESCALATE

    def test_passed_true_overrides_inconsistent_action(self):
        """passed=True silently corrects non-ACCEPT action to ACCEPT."""
        r = VerifyResult(passed=True, action=VerifyAction.RETRY)
        assert r.action == VerifyAction.ACCEPT

        r2 = VerifyResult(passed=True, action=VerifyAction.BLOCK)
        assert r2.action == VerifyAction.ACCEPT

    def test_construction_with_all_fields(self):
        r = VerifyResult(
            passed=False,
            action=VerifyAction.BLOCK,
            message="Constraint violated",
            details={"verifier_name": "safety_check"},
            metadata={"disallowed_tools": ["rm"]},
        )
        assert r.passed is False
        assert r.action == VerifyAction.BLOCK
        assert r.message == "Constraint violated"
        assert r.details["verifier_name"] == "safety_check"
        assert r.metadata["disallowed_tools"] == ["rm"]


# ─── Serialization round-trip ─────────────────────────────────


class TestSerialization:
    """Verify types work with dataclasses.asdict for JSON serialization."""

    def test_task_asdict(self):
        from dataclasses import asdict

        t = Task(id="t1", description="desc", metadata={"k": "v"})
        d = asdict(t)
        assert d == {"id": "t1", "description": "desc", "metadata": {"k": "v"}}

    def test_epoch_state_asdict(self):
        from dataclasses import asdict

        s = EpochState(epoch=2, completed_tasks=["t1"])
        d = asdict(s)
        assert d["epoch"] == 2
        assert d["completed_tasks"] == ["t1"]

    def test_verify_result_asdict_preserves_action(self):
        from dataclasses import asdict

        r = VerifyResult(passed=True)
        d = asdict(r)
        assert d["action"] == VerifyAction.ACCEPT
