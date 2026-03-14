"""Built-in harness templates — discovery, inspection, and copy API.

Provides ``list_templates()``, ``get_template_dir()``, and
``copy_template()`` for working with the bundled harness configuration
templates.
"""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path


def _templates_root() -> Path:
    """Return the filesystem path to the templates package directory."""
    return Path(importlib.resources.files("rigger.templates").__fspath__())  # type: ignore[union-attr]


def list_templates() -> list[str]:
    """Return sorted names of available built-in templates.

    Each name corresponds to a subdirectory under ``rigger/templates/``
    that contains at least a ``harness.yaml``.

    Returns:
        Sorted list of template names.
    """
    root = _templates_root()
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "harness.yaml").exists()
    )


def get_template_dir(name: str) -> Path:
    """Return the filesystem path to a named template directory.

    Args:
        name: Template name (e.g. ``"openai"`` or ``"gsd"``).

    Returns:
        Path to the template directory.

    Raises:
        KeyError: If no template with *name* exists.
    """
    root = _templates_root()
    template_dir = root / name
    if not template_dir.is_dir() or not (template_dir / "harness.yaml").exists():
        available = list_templates()
        msg = (
            f"Unknown template {name!r}. "
            f"Available: {', '.join(available) if available else '(none)'}"
        )
        raise KeyError(msg)
    return template_dir


def copy_template(name: str, dest: Path) -> list[Path]:
    """Copy a template's files into *dest*, preserving directory structure.

    Existing files are **not** overwritten — they are skipped with a
    warning printed to stderr.

    Args:
        name: Template name (e.g. ``"openai"`` or ``"gsd"``).
        dest: Destination directory (created if it does not exist).

    Returns:
        List of created file paths (relative to *dest*).

    Raises:
        KeyError: If no template with *name* exists.
    """
    src_dir = get_template_dir(name)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        # Skip __pycache__ and .pyc files
        if "__pycache__" in src_file.parts or src_file.suffix == ".pyc":
            continue
        rel = src_file.relative_to(src_dir)
        dst_file = dest / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        created.append(rel)

    return created
