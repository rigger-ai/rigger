"""Tests for rigger._merge — metadata merge algorithm."""

import logging

from rigger._merge import merge_metadata
from rigger._types import VerifyResult

# ─── Empty / Single Input ────────────────────────────────────


class TestEmptyInput:
    def test_no_results(self):
        assert merge_metadata([]) == {}

    def test_single_result_no_metadata(self):
        r = VerifyResult(passed=True, metadata={})
        assert merge_metadata([r]) == {}

    def test_single_result_passthrough(self):
        r = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": ["mcp__git__*"],
                "disallowed_tools": ["rm"],
                "max_iterations": 50,
                "acme.custom": True,
            },
        )
        result = merge_metadata([r])
        assert result == {
            "allowed_tools": ["mcp__git__*"],
            "disallowed_tools": ["rm"],
            "max_iterations": 50,
            "acme.custom": True,
        }


# ─── Restrictive Merge (allowed_tools) ──────────────────────


class TestRestrictiveMerge:
    def test_intersection_two_constraints(self):
        r1 = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": [
                    "mcp__git__*",
                    "mcp__verify__*",
                    "mcp__bash__run",
                ],
            },
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["mcp__git__*", "mcp__bash__run"]},
        )
        result = merge_metadata([r1, r2])
        assert result["allowed_tools"] == ["mcp__bash__run", "mcp__git__*"]

    def test_intersection_three_constraints(self):
        r1 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["a", "b", "c"]},
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["b", "c", "d"]},
        )
        r3 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["c", "d", "e"]},
        )
        result = merge_metadata([r1, r2, r3])
        assert result["allowed_tools"] == ["c"]

    def test_empty_list_is_identity(self):
        """Empty list means 'no opinion' — does not participate in intersection."""
        r1 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": []},
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["mcp__git__*"]},
        )
        result = merge_metadata([r1, r2])
        assert result["allowed_tools"] == ["mcp__git__*"]

    def test_all_empty_lists(self):
        r1 = VerifyResult(passed=True, metadata={"allowed_tools": []})
        r2 = VerifyResult(passed=True, metadata={"allowed_tools": []})
        result = merge_metadata([r1, r2])
        assert result["allowed_tools"] == []

    def test_disjoint_sets_produce_empty(self, caplog):
        r1 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["a", "b"]},
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["c", "d"]},
        )
        with caplog.at_level(logging.WARNING):
            result = merge_metadata([r1, r2])
        assert result["allowed_tools"] == []
        assert "empty set" in caplog.text

    def test_output_is_sorted(self):
        r = VerifyResult(
            passed=True,
            metadata={"allowed_tools": ["z", "a", "m"]},
        )
        result = merge_metadata([r])
        assert result["allowed_tools"] == ["a", "m", "z"]


# ─── Additive Merge (disallowed_tools) ──────────────────────


class TestAdditiveMerge:
    def test_union_two_constraints(self):
        r1 = VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["rm", "curl"]},
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["wget", "ssh"]},
        )
        result = merge_metadata([r1, r2])
        assert result["disallowed_tools"] == ["curl", "rm", "ssh", "wget"]

    def test_union_deduplicates(self):
        r1 = VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["rm", "curl"]},
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["rm", "wget"]},
        )
        result = merge_metadata([r1, r2])
        assert result["disallowed_tools"] == ["curl", "rm", "wget"]

    def test_empty_list_union(self):
        r1 = VerifyResult(passed=True, metadata={"disallowed_tools": []})
        r2 = VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["rm"]},
        )
        result = merge_metadata([r1, r2])
        assert result["disallowed_tools"] == ["rm"]

    def test_output_is_sorted(self):
        r = VerifyResult(
            passed=True,
            metadata={"disallowed_tools": ["z", "a", "m"]},
        )
        result = merge_metadata([r])
        assert result["disallowed_tools"] == ["a", "m", "z"]


# ─── Scalar-Min Merge (max_iterations) ──────────────────────


class TestScalarMinMerge:
    def test_minimum_wins(self):
        r1 = VerifyResult(passed=True, metadata={"max_iterations": 50})
        r2 = VerifyResult(passed=True, metadata={"max_iterations": 30})
        result = merge_metadata([r1, r2])
        assert result["max_iterations"] == 30

    def test_none_is_identity(self):
        r1 = VerifyResult(passed=True, metadata={"max_iterations": None})
        r2 = VerifyResult(passed=True, metadata={"max_iterations": 50})
        result = merge_metadata([r1, r2])
        assert result["max_iterations"] == 50

    def test_all_none(self):
        r1 = VerifyResult(passed=True, metadata={"max_iterations": None})
        r2 = VerifyResult(passed=True, metadata={"max_iterations": None})
        result = merge_metadata([r1, r2])
        assert result["max_iterations"] is None

    def test_single_value(self):
        r = VerifyResult(passed=True, metadata={"max_iterations": 42})
        result = merge_metadata([r])
        assert result["max_iterations"] == 42


# ─── Custom Keys (last-writer-wins) ─────────────────────────


class TestCustomKeys:
    def test_single_custom_key(self):
        r = VerifyResult(
            passed=True,
            metadata={"acme.require_signed_commits": True},
        )
        result = merge_metadata([r])
        assert result["acme.require_signed_commits"] is True

    def test_last_writer_wins(self, caplog):
        r1 = VerifyResult(
            passed=True,
            metadata={"acme.threshold": 0.5},
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"acme.threshold": 0.25},
        )
        with caplog.at_level(logging.INFO):
            result = merge_metadata([r1, r2])
        assert result["acme.threshold"] == 0.25
        assert "acme.threshold" in caplog.text
        assert "2 constraints" in caplog.text

    def test_no_warning_for_single_writer(self, caplog):
        r = VerifyResult(
            passed=True,
            metadata={"vendor.key": "value"},
        )
        with caplog.at_level(logging.INFO):
            merge_metadata([r])
        assert "vendor.key" not in caplog.text

    def test_reserved_underscore_keys_passthrough(self):
        """Underscore-prefixed keys use last-writer-wins like custom keys."""
        r = VerifyResult(
            passed=True,
            metadata={"_internal": "data"},
        )
        result = merge_metadata([r])
        assert result["_internal"] == "data"


# ─── Mixed Merge (full scenario from Task 1.26 §7) ──────────


class TestMixedMerge:
    def test_full_scenario(self):
        """Three-constraint example from Task 1.26 §7."""
        r1 = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": ["mcp__git__*", "mcp__verify__*", "mcp__bash__run"],
                "disallowed_tools": ["rm", "curl"],
            },
        )
        r2 = VerifyResult(
            passed=True,
            metadata={"max_iterations": 50},
        )
        r3 = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": ["mcp__git__*", "mcp__bash__run"],
                "disallowed_tools": ["wget", "ssh"],
                "max_iterations": 30,
                "acme.require_signed_commits": True,
            },
        )
        result = merge_metadata([r1, r2, r3])
        assert result == {
            "allowed_tools": ["mcp__bash__run", "mcp__git__*"],
            "disallowed_tools": ["curl", "rm", "ssh", "wget"],
            "max_iterations": 30,
            "acme.require_signed_commits": True,
        }


# ─── Determinism ─────────────────────────────────────────────


class TestDeterminism:
    def test_order_independent_for_standard_keys(self):
        """Same results in different order produce identical output."""
        r1 = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": ["a", "b", "c"],
                "disallowed_tools": ["x"],
                "max_iterations": 50,
            },
        )
        r2 = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": ["b", "c", "d"],
                "disallowed_tools": ["y"],
                "max_iterations": 30,
            },
        )
        forward = merge_metadata([r1, r2])
        reverse = merge_metadata([r2, r1])
        assert forward == reverse

    def test_sorted_output_lists(self):
        r1 = VerifyResult(
            passed=True,
            metadata={
                "allowed_tools": ["z", "a"],
                "disallowed_tools": ["z", "a"],
            },
        )
        result = merge_metadata([r1])
        assert result["allowed_tools"] == ["a", "z"]
        assert result["disallowed_tools"] == ["a", "z"]
