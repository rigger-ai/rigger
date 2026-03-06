"""HarnessDirStateStore — delegates to .harness/state.json schema utilities.

Config name: ``harness_dir``

Corpus pattern SC-3: Uses the built-in ``.harness/state.json`` location.
This is the **default** StateStore when none is explicitly configured.
"""

from __future__ import annotations

from pathlib import Path

from rigger._schema import read_state, write_state
from rigger._types import EpochState


class HarnessDirStateStore:
    """Persists ``EpochState`` via ``.harness/state.json``.

    Thin wrapper around ``rigger._schema.read_state()`` and
    ``write_state()``. This is functionally equivalent to the
    default behavior when no StateStore is configured, but
    exists as an explicit class for the declarative registry.
    """

    def load(self, project_root: Path) -> EpochState:
        """Load state from ``.harness/state.json``."""
        return read_state(project_root)

    def save(self, project_root: Path, state: EpochState) -> None:
        """Write state to ``.harness/state.json``."""
        write_state(project_root, state)
