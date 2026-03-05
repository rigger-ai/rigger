"""ContextProvisioner — aggregates ContextSource results.

Single-class design validated in Task 1.7 (no hierarchy). Holds a flat
list of ContextSource objects and merges their gather() results into a
single ProvisionResult. CriticalSource wrapper provides fail-stop escape
hatch for sources whose absence makes context dangerously incomplete.

Source: Strawman API v2 §3.5, Task 1.7 (single-class validation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from rigger._protocols import ContextSource
from rigger._types import ProvisionResult

logger = logging.getLogger(__name__)


@dataclass
class ContextProvisioner:
    """Aggregates multiple ContextSource instances into a single ProvisionResult.

    Holds a flat list of ContextSource objects — no subclasses, no type
    hierarchy, no participation-mode distinction at the type level. Active
    provisioners and registration stubs are treated uniformly: call
    gather(), merge results.

    Design decisions (Task 1.7):
        1. Files are deduplicated by resolved path (preserve first-seen order).
        2. Capabilities are concatenated in source order (no dedup).
        3. Failing sources are logged and skipped (fail-open default).
           Use CriticalSource wrapper for fail-stop override.
        4. Sources are called sequentially in list order.
    """

    sources: list[ContextSource] = field(default_factory=list)

    def provision(self, project_root: Path) -> ProvisionResult:
        """Call gather() on each source, merge results into one ProvisionResult.

        Args:
            project_root: The project directory.

        Returns:
            Aggregated ProvisionResult with deduplicated files and
            concatenated capabilities.
        """
        all_files: list[Path] = []
        seen_paths: dict[Path, str] = {}  # resolved_path -> source class name
        all_capabilities: list[str] = []

        for source in self.sources:
            try:
                result = source.gather(project_root)
            except Exception as exc:
                if isinstance(source, CriticalSource):
                    raise
                logger.warning(
                    "ContextSource %s.gather() raised %s: %s — skipping",
                    type(source).__name__,
                    type(exc).__name__,
                    exc,
                )
                continue

            for f in result.files:
                resolved = f.resolve()
                if resolved not in seen_paths:
                    seen_paths[resolved] = type(source).__name__
                    all_files.append(f)
                else:
                    logger.warning(
                        "Duplicate file path %s from %s (first seen from %s) — skipped",
                        f,
                        type(source).__name__,
                        seen_paths[resolved],
                    )

            all_capabilities.extend(result.capabilities)

        return ProvisionResult(files=all_files, capabilities=all_capabilities)


class CriticalSource:
    """Wrapper that makes a ContextSource's failure abort provision().

    When a CriticalSource's gather() fails, the exception propagates
    instead of being swallowed. Use this when a source's absence makes
    the agent's context dangerously incomplete.

    The provisioner checks isinstance(source, CriticalSource) before
    catching exceptions. This is a type-level check, not a protocol
    method — the ContextSource protocol remains single-method.

    Usage::

        provisioner = ContextProvisioner(sources=[
            CriticalSource(InitializerProgressSource()),  # fail-stop
            ExternalIssueTrackerSource("PROJ-42"),        # fail-open
        ])
    """

    def __init__(self, inner: ContextSource) -> None:
        self._inner = inner

    def gather(self, project_root: Path) -> ProvisionResult:
        """Delegate to wrapped source. Exceptions propagate uncaught."""
        return self._inner.gather(project_root)
