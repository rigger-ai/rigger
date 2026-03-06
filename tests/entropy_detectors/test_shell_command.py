"""Tests for ShellCommandEntropyDetector."""

from __future__ import annotations

import json
from pathlib import Path

from rigger.entropy_detectors.shell_command import ShellCommandEntropyDetector


class TestScan:
    def test_parses_valid_json_array(self, tmp_path: Path):
        findings = [
            {"description": "Fix stale docs", "priority": "high"},
            {"description": "Update README"},
        ]
        script = tmp_path / "scanner.sh"
        script.write_text(f"#!/bin/sh\necho '{json.dumps(findings)}'")
        script.chmod(0o755)

        detector = ShellCommandEntropyDetector(command=str(script))
        tasks = detector.scan(tmp_path)

        assert len(tasks) == 2
        assert tasks[0].description == "Fix stale docs"
        assert tasks[0].metadata["priority"] == "high"
        assert tasks[0].metadata["source"] == "entropy_scan"
        assert tasks[1].description == "Update README"
        assert "priority" not in tasks[1].metadata

    def test_returns_empty_on_no_output(self, tmp_path: Path):
        detector = ShellCommandEntropyDetector(command="echo ''")
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_returns_empty_on_malformed_json(self, tmp_path: Path):
        detector = ShellCommandEntropyDetector(command="echo '{not json'")
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_returns_empty_on_non_array_json(self, tmp_path: Path):
        detector = ShellCommandEntropyDetector(command='echo \'{"key": "value"}\'')
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_returns_empty_on_nonzero_exit(self, tmp_path: Path):
        detector = ShellCommandEntropyDetector(command="exit 1")
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_returns_empty_on_timeout(self, tmp_path: Path):
        detector = ShellCommandEntropyDetector(command="sleep 10", timeout=1)
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_skips_items_without_description(self, tmp_path: Path):
        findings = [{"priority": "high"}, {"description": "Valid task"}]
        detector = ShellCommandEntropyDetector(command=f"echo '{json.dumps(findings)}'")
        tasks = detector.scan(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].description == "Valid task"

    def test_skips_non_object_items(self, tmp_path: Path):
        findings = ["just a string", {"description": "Valid task"}]
        detector = ShellCommandEntropyDetector(command=f"echo '{json.dumps(findings)}'")
        tasks = detector.scan(tmp_path)
        assert len(tasks) == 1

    def test_runs_from_project_root(self, tmp_path: Path):
        detector = ShellCommandEntropyDetector(command="echo '[]' && pwd")
        # Just verify it doesn't error -- the command runs in tmp_path
        tasks = detector.scan(tmp_path)
        assert tasks == []

    def test_task_ids_are_sequential(self, tmp_path: Path):
        findings = [
            {"description": "First"},
            {"description": "Second"},
            {"description": "Third"},
        ]
        detector = ShellCommandEntropyDetector(command=f"echo '{json.dumps(findings)}'")
        tasks = detector.scan(tmp_path)
        assert [t.id for t in tasks] == ["entropy-0", "entropy-1", "entropy-2"]


class TestProtocolConformance:
    def test_satisfies_entropy_detector_protocol(self):
        from rigger._protocols import EntropyDetector

        detector: EntropyDetector = ShellCommandEntropyDetector(command="echo '[]'")
        assert hasattr(detector, "scan")
