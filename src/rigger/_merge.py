"""Metadata merge algorithm for VerifyResult constraint aggregation.

Merges metadata from multiple Constraint.check() results into a single
config dict for .harness/constraints.json. Each standard key has a
registered merge family that determines how conflicting values combine.

Source: Task 1.26 (VerifyResult Metadata Schema), Strawman API v2 §3.7.
"""

from __future__ import annotations

import logging
from typing import Any

from rigger._types import VerifyResult

logger = logging.getLogger(__name__)

# ─── Merge Family Registry ───────────────────────────────────

# Maps standard keys to their merge family name.
# Unknown keys fall back to last-writer-wins with an INFO log.
_MERGE_FAMILIES: dict[str, str] = {
    "allowed_tools": "restrictive",
    "disallowed_tools": "additive",
    "max_iterations": "scalar_min",
}


# ─── Public API ──────────────────────────────────────────────


def merge_metadata(results: list[VerifyResult]) -> dict[str, Any]:
    """Merge metadata from multiple constraint results into a single config.

    Deterministic: same inputs always produce same output regardless of
    constraint evaluation order. Achieved by commutative set operations
    for lists, commutative min() for scalars, and sorted output.

    Args:
        results: VerifyResult instances from Constraint.check() calls.

    Returns:
        Merged metadata dict ready for .harness/constraints.json.
    """
    # Phase 1: Collect all metadata values per key, preserving source order.
    key_values: dict[str, list[Any]] = {}
    for result in results:
        for key, value in result.metadata.items():
            key_values.setdefault(key, []).append(value)

    # Phase 2: Merge each key according to its family.
    merged: dict[str, Any] = {}

    for key, values in key_values.items():
        family = _MERGE_FAMILIES.get(key)

        if family == "restrictive":
            merged[key] = _merge_restrictive(key, values)
        elif family == "additive":
            merged[key] = _merge_additive(values)
        elif family == "scalar_min":
            merged[key] = _merge_scalar_min(values)
        else:
            # Unknown key — last-writer-wins with INFO log on conflict.
            if len(values) > 1:
                logger.info(
                    "Metadata key '%s' set by %d constraints; "
                    "using last value (no merge family registered)",
                    key,
                    len(values),
                )
            merged[key] = values[-1]

    return merged


# ─── Merge Family Implementations ────────────────────────────


def _merge_restrictive(key: str, values: list[list[str]]) -> list[str]:
    """Intersection of non-empty lists. Empty list = identity (no opinion).

    Uses exact string matching. Constraints sharing this key MUST use
    consistent pattern vocabulary for the intersection to be meaningful.
    """
    participating = [set(v) for v in values if v]
    if not participating:
        return []
    result = participating[0]
    for s in participating[1:]:
        result = result & s
    if not result and len(participating) > 1:
        logger.warning(
            "Metadata key '%s': intersection of %d constraints produced "
            "empty set — agent will have no permitted tools",
            key,
            len(participating),
        )
    return sorted(result)


def _merge_additive(values: list[list[str]]) -> list[str]:
    """Union of all lists."""
    result: set[str] = set()
    for v in values:
        result.update(v)
    return sorted(result)


def _merge_scalar_min(values: list[Any]) -> int | None:
    """Minimum of non-None values. None = identity (no opinion)."""
    non_none = [v for v in values if v is not None]
    if not non_none:
        return None
    return min(non_none)
