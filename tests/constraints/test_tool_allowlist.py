"""Tests for ToolAllowlistConstraint."""

from __future__ import annotations

from pathlib import Path

from rigger._types import VerifyAction
from rigger.constraints.tool_allowlist import ToolAllowlistConstraint


class TestAlwaysPasses:
    def test_passes_with_allowed(self, tmp_path: Path):
        c = ToolAllowlistConstraint(allowed=["Bash", "Read"])
        result = c.check(tmp_path)
        assert result.passed is True
        assert result.action == VerifyAction.ACCEPT

    def test_passes_with_disallowed(self, tmp_path: Path):
        c = ToolAllowlistConstraint(disallowed=["rm", "curl"])
        result = c.check(tmp_path)
        assert result.passed is True

    def test_passes_with_both(self, tmp_path: Path):
        c = ToolAllowlistConstraint(
            allowed=["Bash", "Read"],
            disallowed=["rm"],
        )
        result = c.check(tmp_path)
        assert result.passed is True

    def test_passes_with_neither(self, tmp_path: Path):
        c = ToolAllowlistConstraint()
        result = c.check(tmp_path)
        assert result.passed is True


class TestMetadataKeys:
    def test_allowed_tools_in_metadata(self, tmp_path: Path):
        c = ToolAllowlistConstraint(allowed=["Bash", "Read", "Write"])
        result = c.check(tmp_path)
        assert result.metadata["allowed_tools"] == ["Bash", "Read", "Write"]

    def test_disallowed_tools_in_metadata(self, tmp_path: Path):
        c = ToolAllowlistConstraint(disallowed=["rm", "curl"])
        result = c.check(tmp_path)
        assert result.metadata["disallowed_tools"] == ["rm", "curl"]

    def test_both_keys_in_metadata(self, tmp_path: Path):
        c = ToolAllowlistConstraint(
            allowed=["Bash"],
            disallowed=["rm"],
        )
        result = c.check(tmp_path)
        assert result.metadata["allowed_tools"] == ["Bash"]
        assert result.metadata["disallowed_tools"] == ["rm"]

    def test_empty_lists_omitted_from_metadata(self, tmp_path: Path):
        c = ToolAllowlistConstraint()
        result = c.check(tmp_path)
        assert "allowed_tools" not in result.metadata
        assert "disallowed_tools" not in result.metadata

    def test_allowed_only_omits_disallowed(self, tmp_path: Path):
        c = ToolAllowlistConstraint(allowed=["Bash"])
        result = c.check(tmp_path)
        assert "allowed_tools" in result.metadata
        assert "disallowed_tools" not in result.metadata


class TestProtocolConformance:
    def test_satisfies_constraint_protocol(self):
        from rigger._protocols import Constraint

        c: Constraint = ToolAllowlistConstraint(allowed=["Bash"])
        assert hasattr(c, "check")
