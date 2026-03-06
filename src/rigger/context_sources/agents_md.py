"""AgentsMdContextSource — generates or updates AGENTS.md from a template.

Config name: ``agents_md``

Corpus pattern CP-2: Repo-as-system-of-record.
Sources: C2 (OpenAI), C13 (Codex CLI).
"""

from __future__ import annotations

import logging
from pathlib import Path

from rigger._types import ProvisionResult

logger = logging.getLogger(__name__)


class AgentsMdContextSource:
    """Generates or updates an AGENTS.md file from a template.

    The template supports variable substitution with ``{task}``,
    ``{constraints}``, and ``{context}`` placeholders. Unresolved
    placeholders are left as-is.

    The ``template`` argument may be either an inline string or a
    path to a template file. If it starts with ``/`` or ends with
    ``.md`` / ``.txt``, it is treated as a file path; otherwise as
    an inline template string.

    Args:
        template: Inline template string or path to a template file.
        output: Output filename relative to project root (default: ``"AGENTS.md"``).
        variables: Optional dict of variable substitutions beyond the standard ones.
    """

    def __init__(  # noqa: D107
        self,
        template: str,
        *,
        output: str = "AGENTS.md",
        variables: dict[str, str] | None = None,
    ) -> None:
        self._template = template
        self._output = output
        self._variables = variables or {}

    def gather(self, project_root: Path) -> ProvisionResult:
        """Write AGENTS.md to project root from template, return its path.

        Reads the template (from file or inline), applies variable
        substitution, and writes the output file. Returns the path
        in ``ProvisionResult.files``.
        """
        template_content = self._load_template(project_root)
        if template_content is None:
            return ProvisionResult()

        rendered = self._render(template_content)

        output_path = project_root / self._output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")

        return ProvisionResult(files=[output_path])

    def _load_template(self, project_root: Path) -> str | None:
        """Load template content from file path or return inline string."""
        if self._is_file_path(self._template):
            template_path = Path(self._template)
            if not template_path.is_absolute():
                template_path = project_root / template_path
            if not template_path.exists():
                logger.warning("Template file %s does not exist", template_path)
                return None
            return template_path.read_text(encoding="utf-8")
        return self._template

    def _render(self, content: str) -> str:
        """Apply variable substitution to template content.

        Standard variables (``{task}``, ``{constraints}``, ``{context}``)
        default to empty strings if not provided. Additional variables
        from the constructor are also applied.
        """
        defaults = {"task": "", "constraints": "", "context": ""}
        merged = {**defaults, **self._variables}
        for key, value in merged.items():
            content = content.replace(f"{{{key}}}", value)
        return content

    @staticmethod
    def _is_file_path(template: str) -> bool:
        """Heuristic: treat as file path if absolute or has a file extension."""
        return (
            template.startswith("/")
            or template.endswith(".md")
            or template.endswith(".txt")
        )
