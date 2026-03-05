"""Tests for ContextProvisioner and CriticalSource."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from rigger._provisioner import ContextProvisioner, CriticalSource
from rigger._types import ProvisionResult

# ─── Helpers ─────────────────────────────────────────────────


class StubSource:
    """ContextSource that returns a fixed ProvisionResult."""

    def __init__(
        self,
        files: list[Path] | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        self._result = ProvisionResult(
            files=files or [],
            capabilities=capabilities or [],
        )

    def gather(self, project_root: Path) -> ProvisionResult:
        return self._result


class FailingSource:
    """ContextSource that always raises."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or RuntimeError("boom")

    def gather(self, project_root: Path) -> ProvisionResult:
        raise self._exc


class TrackingSource:
    """ContextSource that records calls."""

    def __init__(self, result: ProvisionResult | None = None) -> None:
        self._result = result or ProvisionResult()
        self.calls: list[Path] = []

    def gather(self, project_root: Path) -> ProvisionResult:
        self.calls.append(project_root)
        return self._result


# ─── Basic aggregation ───────────────────────────────────────


class TestBasicAggregation:
    def test_empty_sources(self, tmp_path: Path) -> None:
        prov = ContextProvisioner(sources=[])
        result = prov.provision(tmp_path)
        assert result.files == []
        assert result.capabilities == []

    def test_single_source_files(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.touch()
        prov = ContextProvisioner(sources=[StubSource(files=[f])])
        result = prov.provision(tmp_path)
        assert result.files == [f]
        assert result.capabilities == []

    def test_single_source_capabilities(self, tmp_path: Path) -> None:
        prov = ContextProvisioner(sources=[StubSource(capabilities=["Linear API"])])
        result = prov.provision(tmp_path)
        assert result.files == []
        assert result.capabilities == ["Linear API"]

    def test_multiple_sources_merge(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.touch()
        f2.touch()
        prov = ContextProvisioner(
            sources=[
                StubSource(files=[f1], capabilities=["cap1"]),
                StubSource(files=[f2], capabilities=["cap2"]),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f1, f2]
        assert result.capabilities == ["cap1", "cap2"]

    def test_capabilities_preserve_order(self, tmp_path: Path) -> None:
        prov = ContextProvisioner(
            sources=[
                StubSource(capabilities=["c1", "c2"]),
                StubSource(capabilities=["c3"]),
                StubSource(capabilities=["c4", "c5"]),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.capabilities == ["c1", "c2", "c3", "c4", "c5"]

    def test_sources_called_with_project_root(self, tmp_path: Path) -> None:
        t1 = TrackingSource()
        t2 = TrackingSource()
        prov = ContextProvisioner(sources=[t1, t2])
        prov.provision(tmp_path)
        assert t1.calls == [tmp_path]
        assert t2.calls == [tmp_path]


# ─── Deduplication ───────────────────────────────────────────


class TestDeduplication:
    def test_duplicate_paths_deduped(self, tmp_path: Path) -> None:
        f = tmp_path / "same.txt"
        f.touch()
        prov = ContextProvisioner(
            sources=[StubSource(files=[f]), StubSource(files=[f])]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f]

    def test_duplicate_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        f = tmp_path / "same.txt"
        f.touch()
        prov = ContextProvisioner(
            sources=[StubSource(files=[f]), StubSource(files=[f])]
        )
        with caplog.at_level(logging.WARNING):
            prov.provision(tmp_path)
        assert "Duplicate file path" in caplog.text
        assert "first seen from" in caplog.text

    def test_different_paths_not_deduped(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.touch()
        f2.touch()
        prov = ContextProvisioner(
            sources=[StubSource(files=[f1]), StubSource(files=[f2])]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f1, f2]

    def test_first_seen_wins(self, tmp_path: Path) -> None:
        """First source's file is kept, second's duplicate is dropped."""
        f = tmp_path / "shared.txt"
        f.touch()
        extra = tmp_path / "extra.txt"
        extra.touch()
        prov = ContextProvisioner(
            sources=[
                StubSource(files=[f]),
                StubSource(files=[f, extra]),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f, extra]

    def test_symlink_dedup(self, tmp_path: Path) -> None:
        """Symlinks resolving to the same file are deduplicated."""
        real = tmp_path / "real.txt"
        real.touch()
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        prov = ContextProvisioner(
            sources=[StubSource(files=[real]), StubSource(files=[link])]
        )
        result = prov.provision(tmp_path)
        assert len(result.files) == 1


# ─── Fail-open error handling ────────────────────────────────


class TestFailOpen:
    def test_failing_source_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "good.txt"
        f.touch()
        prov = ContextProvisioner(
            sources=[
                StubSource(files=[f]),
                FailingSource(),
                StubSource(capabilities=["cap"]),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f]
        assert result.capabilities == ["cap"]

    def test_failing_source_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        prov = ContextProvisioner(sources=[FailingSource(ValueError("oops"))])
        with caplog.at_level(logging.WARNING):
            prov.provision(tmp_path)
        assert "FailingSource" in caplog.text
        assert "ValueError" in caplog.text
        assert "oops" in caplog.text

    def test_all_sources_fail(self, tmp_path: Path) -> None:
        prov = ContextProvisioner(sources=[FailingSource(), FailingSource()])
        result = prov.provision(tmp_path)
        assert result.files == []
        assert result.capabilities == []

    def test_sources_after_failure_still_run(self, tmp_path: Path) -> None:
        tracker = TrackingSource(ProvisionResult(capabilities=["alive"]))
        prov = ContextProvisioner(sources=[FailingSource(), tracker])
        result = prov.provision(tmp_path)
        assert tracker.calls == [tmp_path]
        assert result.capabilities == ["alive"]


# ─── CriticalSource ──────────────────────────────────────────


class TestCriticalSource:
    def test_delegates_to_inner(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.touch()
        inner = StubSource(files=[f], capabilities=["cap"])
        cs = CriticalSource(inner)
        result = cs.gather(tmp_path)
        assert result.files == [f]
        assert result.capabilities == ["cap"]

    def test_critical_failure_propagates(self, tmp_path: Path) -> None:
        cs = CriticalSource(FailingSource(RuntimeError("fatal")))
        prov = ContextProvisioner(sources=[cs])
        with pytest.raises(RuntimeError, match="fatal"):
            prov.provision(tmp_path)

    def test_non_critical_skipped_critical_propagates(self, tmp_path: Path) -> None:
        """Non-critical fails silently, critical failure aborts."""
        prov = ContextProvisioner(
            sources=[
                FailingSource(ValueError("ignored")),
                CriticalSource(FailingSource(RuntimeError("fatal"))),
            ]
        )
        with pytest.raises(RuntimeError, match="fatal"):
            prov.provision(tmp_path)

    def test_critical_success_with_others(self, tmp_path: Path) -> None:
        f1 = tmp_path / "critical.txt"
        f2 = tmp_path / "normal.txt"
        f1.touch()
        f2.touch()
        prov = ContextProvisioner(
            sources=[
                CriticalSource(StubSource(files=[f1])),
                StubSource(files=[f2]),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f1, f2]

    def test_sources_before_critical_failure_contribute(self, tmp_path: Path) -> None:
        """Sources that ran before the critical failure still contributed."""
        f = tmp_path / "before.txt"
        f.touch()
        prov = ContextProvisioner(
            sources=[
                StubSource(files=[f]),
                CriticalSource(FailingSource(RuntimeError("abort"))),
            ]
        )
        with pytest.raises(RuntimeError, match="abort"):
            prov.provision(tmp_path)


# ─── Empty / edge cases ─────────────────────────────────────


class TestEdgeCases:
    def test_empty_provision_result_from_source(self, tmp_path: Path) -> None:
        prov = ContextProvisioner(sources=[StubSource()])
        result = prov.provision(tmp_path)
        assert result.files == []
        assert result.capabilities == []

    def test_mixed_empty_and_non_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.touch()
        prov = ContextProvisioner(
            sources=[
                StubSource(),
                StubSource(files=[f], capabilities=["cap"]),
                StubSource(),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.files == [f]
        assert result.capabilities == ["cap"]

    def test_many_sources(self, tmp_path: Path) -> None:
        sources = []
        expected_files = []
        for i in range(10):
            f = tmp_path / f"file_{i}.txt"
            f.touch()
            sources.append(StubSource(files=[f], capabilities=[f"cap_{i}"]))
            expected_files.append(f)

        prov = ContextProvisioner(sources=sources)
        result = prov.provision(tmp_path)
        assert result.files == expected_files
        assert result.capabilities == [f"cap_{i}" for i in range(10)]

    def test_duplicate_capabilities_not_deduped(self, tmp_path: Path) -> None:
        """Capabilities are NOT deduplicated — intentional design choice."""
        prov = ContextProvisioner(
            sources=[
                StubSource(capabilities=["same"]),
                StubSource(capabilities=["same"]),
            ]
        )
        result = prov.provision(tmp_path)
        assert result.capabilities == ["same", "same"]
