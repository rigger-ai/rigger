"""ToolAllowlistConstraint — emits tool restriction metadata for the backend.

Config name: ``tool_allowlist``

Corpus pattern AC-3: Tool allowlist/denylist as constraint metadata.
Sources: C8 (Spotify strict allowlist), Task 1.26 (metadata schema).
"""

from __future__ import annotations

import logging
from pathlib import Path

from rigger._types import VerifyResult

logger = logging.getLogger(__name__)


class ToolAllowlistConstraint:
    """Emits ``allowed_tools`` and/or ``disallowed_tools`` metadata.

    This constraint always passes — it is metadata-emitting, not blocking.
    The emitted metadata flows through the merge algorithm (Task 1.26) into
    ``.harness/constraints.json`` for the backend to read.

    Args:
        allowed: Tool names/patterns the agent MAY use. Empty means no opinion.
        disallowed: Tool names/patterns the agent MUST NOT use. Empty means
            no opinion.
    """

    def __init__(
        self,
        allowed: list[str] | None = None,
        disallowed: list[str] | None = None,
    ) -> None:
        self._allowed = list(allowed) if allowed else []
        self._disallowed = list(disallowed) if disallowed else []

    def check(self, project_root: Path) -> VerifyResult:
        """Return tool restriction metadata. Always passes."""
        metadata: dict[str, list[str]] = {}
        if self._allowed:
            metadata["allowed_tools"] = self._allowed
        if self._disallowed:
            metadata["disallowed_tools"] = self._disallowed
        return VerifyResult(passed=True, metadata=metadata)
