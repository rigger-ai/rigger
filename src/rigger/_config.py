"""YAML config loader — parses harness.yaml into a Harness instance.

Provides ``load_config()`` to parse a YAML file into a ``HarnessConfig``
dataclass, and ``build_harness()`` to wire it into a live ``Harness``.
Environment variable interpolation (``${VAR}``) and relative path
resolution are handled transparently.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from rigger._harness import Harness, all_tasks_done
from rigger._registry import registry

if TYPE_CHECKING:
    from collections.abc import Callable

    from rigger._types import EpochState

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

# ${VAR} or ${VAR:-default}
_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")

_VALID_TOP_KEYS = frozenset(
    {
        "backend",
        "task_source",
        "context_sources",
        "verifiers",
        "constraints",
        "state_store",
        "entropy_detectors",
        "workspace",
        "run",
    }
)

# Constructor parameter names that represent filesystem paths.
# Resolved against the config file's directory during build_harness().
_PATH_PARAMS = frozenset({"path", "root", "source", "destination"})

_VALID_STOP_WHEN = frozenset({"all_tasks_done", "max_epochs", "never"})


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class ComponentConfig:
    """Configuration for a single protocol implementation."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunConfig:
    """Loop control parameters from the ``run:`` YAML section."""

    max_epochs: int = 100
    max_retries: int = 3
    stop_when: str = "all_tasks_done"
    inject_entropy_tasks: bool = True


@dataclass
class HarnessConfig:
    """Parsed ``harness.yaml`` configuration."""

    backend: ComponentConfig
    task_source: ComponentConfig
    context_sources: list[ComponentConfig] = field(default_factory=list)
    verifiers: list[ComponentConfig] = field(default_factory=list)
    constraints: list[ComponentConfig] = field(default_factory=list)
    state_store: ComponentConfig | None = None
    entropy_detectors: list[ComponentConfig] = field(default_factory=list)
    workspace: ComponentConfig | None = None
    run: RunConfig = field(default_factory=RunConfig)
    config_dir: Path = field(default_factory=Path.cwd)


# ── Environment variable interpolation ────────────────────────


def _interpolate_env(value: str) -> str:
    """Replace ``${VAR}`` and ``${VAR:-default}`` in a string.

    Args:
        value: String potentially containing env var references.

    Returns:
        String with env vars resolved.

    Raises:
        ValueError: If a referenced env var is unset and has no default.
    """

    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        default = match.group(2)
        val = os.environ.get(var)
        if val is None and default is None:
            msg = f"Environment variable ${{{var}}} is not set"
            raise ValueError(msg)
        return val if val is not None else (default or "")

    return _ENV_PATTERN.sub(_replace, value)


def _interpolate_recursive(obj: Any) -> Any:
    """Walk a data structure, interpolating env vars in all strings."""
    if isinstance(obj, str):
        return _interpolate_env(obj)
    if isinstance(obj, dict):
        return {k: _interpolate_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_recursive(v) for v in obj]
    return obj


# ── Path resolution ───────────────────────────────────────────


def _resolve_paths(params: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    """Resolve known path parameters against *config_dir*.

    Only parameters whose name is in ``_PATH_PARAMS`` and whose value
    is a non-absolute string are resolved.

    Args:
        params: Constructor keyword arguments.
        config_dir: Directory containing the YAML config file.

    Returns:
        A new dict with resolved paths.
    """
    resolved = dict(params)
    for key in _PATH_PARAMS:
        if key in resolved and isinstance(resolved[key], str):
            p = Path(resolved[key])
            if not p.is_absolute():
                resolved[key] = str(config_dir / p)
    return resolved


# ── Parsing helpers ───────────────────────────────────────────


def _parse_component(raw: Any, section: str) -> ComponentConfig:
    """Extract ``type`` and remaining keys from a raw YAML mapping.

    Args:
        raw: Parsed YAML dict for one component.
        section: Section name for error messages (e.g. ``"backend"``).

    Returns:
        A ``ComponentConfig`` with type and params separated.

    Raises:
        ValueError: If *raw* is not a dict or lacks ``type``.
    """
    if not isinstance(raw, dict):
        msg = f"'{section}' must be a mapping, got {type(raw).__name__}"
        raise ValueError(msg)
    raw = dict(raw)  # shallow copy so pop() doesn't mutate caller
    type_name = raw.pop("type", None)
    if type_name is None:
        msg = f"'{section}' is missing required key 'type'"
        raise ValueError(msg)
    if not isinstance(type_name, str):
        msg = f"'{section}.type' must be a string, got {type(type_name).__name__}"
        raise ValueError(msg)
    return ComponentConfig(type=type_name, params=raw)


def _parse_component_list(raw: Any, section: str) -> list[ComponentConfig]:
    """Parse a YAML list of component configs.

    Args:
        raw: Parsed YAML list (or ``None``).
        section: Section name for error messages.

    Returns:
        List of ``ComponentConfig`` objects.

    Raises:
        ValueError: If *raw* is not a list.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        msg = f"'{section}' must be a list, got {type(raw).__name__}"
        raise ValueError(msg)
    return [_parse_component(item, f"{section}[{i}]") for i, item in enumerate(raw)]


def _parse_run(raw: Any) -> RunConfig:
    """Parse the ``run:`` section.

    Args:
        raw: Parsed YAML dict (or ``None``).

    Returns:
        A ``RunConfig`` with validated values.

    Raises:
        ValueError: If types or values are invalid.
    """
    if raw is None:
        return RunConfig()
    if not isinstance(raw, dict):
        msg = f"'run' must be a mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    valid_keys = {"max_epochs", "max_retries", "stop_when", "inject_entropy_tasks"}
    unknown = set(raw.keys()) - valid_keys
    if unknown:
        logger.warning("Unknown keys in 'run': %s", ", ".join(sorted(unknown)))

    stop_when = raw.get("stop_when", "all_tasks_done")
    if stop_when not in _VALID_STOP_WHEN:
        msg = (
            f"Invalid stop_when value {stop_when!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_STOP_WHEN))}"
        )
        raise ValueError(msg)

    return RunConfig(
        max_epochs=raw.get("max_epochs", 100),
        max_retries=raw.get("max_retries", 3),
        stop_when=stop_when,
        inject_entropy_tasks=raw.get("inject_entropy_tasks", True),
    )


# ── Public API ────────────────────────────────────────────────


def load_config(path: Path | str) -> HarnessConfig:
    """Parse a ``harness.yaml`` file into a ``HarnessConfig``.

    Performs environment variable interpolation on all string values
    and validates the top-level structure.

    Args:
        path: Path to the YAML config file.

    Returns:
        Parsed and validated configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the YAML structure is invalid.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Config file not found: {path}"
        raise FileNotFoundError(msg)

    with Path.open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        msg = f"Config file must contain a YAML mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    # Interpolate env vars in all string values
    raw = _interpolate_recursive(raw)

    # Warn on unknown top-level keys
    unknown = set(raw.keys()) - _VALID_TOP_KEYS
    if unknown:
        logger.warning(
            "Unknown top-level keys in config: %s", ", ".join(sorted(unknown))
        )

    # Required fields
    if "backend" not in raw:
        msg = "Missing required key: 'backend'"
        raise ValueError(msg)
    if "task_source" not in raw:
        msg = "Missing required key: 'task_source'"
        raise ValueError(msg)

    config_dir = path.parent.resolve()

    return HarnessConfig(
        backend=_parse_component(raw["backend"], "backend"),
        task_source=_parse_component(raw["task_source"], "task_source"),
        context_sources=_parse_component_list(
            raw.get("context_sources"), "context_sources"
        ),
        verifiers=_parse_component_list(raw.get("verifiers"), "verifiers"),
        constraints=_parse_component_list(raw.get("constraints"), "constraints"),
        state_store=(
            _parse_component(raw["state_store"], "state_store")
            if "state_store" in raw
            else None
        ),
        entropy_detectors=_parse_component_list(
            raw.get("entropy_detectors"), "entropy_detectors"
        ),
        workspace=(
            _parse_component(raw["workspace"], "workspace")
            if "workspace" in raw
            else None
        ),
        run=_parse_run(raw.get("run")),
        config_dir=config_dir,
    )


def get_stop_predicate(name: str) -> Callable[[EpochState], bool]:
    """Map a ``stop_when`` config string to a callable predicate.

    Args:
        name: One of ``"all_tasks_done"``, ``"max_epochs"``, ``"never"``.

    Returns:
        A predicate compatible with ``Harness.run(stop_when=...)``.

    Raises:
        ValueError: If *name* is not a recognized value.
    """
    predicates: dict[str, Callable[[EpochState], bool]] = {
        "all_tasks_done": all_tasks_done,
        "max_epochs": lambda state: False,
        "never": lambda state: False,
    }
    if name not in predicates:
        msg = (
            f"Unknown stop_when value {name!r}. "
            f"Must be one of: {', '.join(sorted(predicates))}"
        )
        raise ValueError(msg)
    return predicates[name]


def build_harness(
    config: HarnessConfig,
    project_root: Path | None = None,
) -> Harness:
    """Build a fully-wired ``Harness`` from a ``HarnessConfig``.

    Uses the global registry to instantiate all components by their
    ``type`` config name.

    Args:
        config: Parsed YAML configuration.
        project_root: Project root directory. Defaults to *config.config_dir*.

    Returns:
        A configured ``Harness`` instance ready to call ``run()`` on.

    Raises:
        KeyError: If a component type is not found in the registry.
        TypeError: If constructor parameters are invalid.
    """
    root = project_root or config.config_dir

    def _create(protocol: str, comp: ComponentConfig) -> Any:
        params = _resolve_paths(comp.params, config.config_dir)
        return registry.create(protocol, comp.type, **params)

    backend = _create("backend", config.backend)
    task_source = _create("task_source", config.task_source)
    context_sources = [_create("context_source", c) for c in config.context_sources]
    verifiers = [_create("verifier", v) for v in config.verifiers]
    constraints = [_create("constraint", c) for c in config.constraints]
    state_store = (
        _create("state_store", config.state_store) if config.state_store else None
    )
    entropy_detectors = [
        _create("entropy_detector", e) for e in config.entropy_detectors
    ]
    workspace = (
        _create("workspace_manager", config.workspace) if config.workspace else None
    )

    return Harness(
        project_root=root,
        backend=backend,
        task_source=task_source,
        context_sources=context_sources or None,
        verifiers=verifiers or None,
        constraints=constraints or None,
        state_store=state_store,
        entropy_detectors=entropy_detectors or None,
        workspace_manager=workspace,
        inject_entropy_tasks=config.run.inject_entropy_tasks,
    )
