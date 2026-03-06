"""Built-in EntropyDetector implementations for codebase entropy detection."""

from rigger.entropy_detectors.doc_staleness import DocStalenessEntropyDetector
from rigger.entropy_detectors.shell_command import ShellCommandEntropyDetector

__all__ = [
    "DocStalenessEntropyDetector",
    "ShellCommandEntropyDetector",
]
