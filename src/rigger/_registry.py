"""Implementation registry — maps config type strings to Python classes.

Enables YAML-driven instantiation of protocol implementations. Built-in
implementations are pre-registered; third-party plugins are discovered
via ``importlib.metadata.entry_points()``.

Usage::

    from rigger._registry import registry

    cls = registry.get("task_source", "file_list")
    instance = registry.create("task_source", "file_list", path="tasks.json")
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Protocol group names used as registry keys and entry point groups.
PROTOCOL_GROUPS = frozenset(
    {
        "task_source",
        "context_source",
        "verifier",
        "constraint",
        "state_store",
        "entropy_detector",
        "workspace_manager",
        "backend",
    }
)


class Registry:
    """Maps ``(protocol, name)`` pairs to implementation classes.

    Built-in implementations are registered at construction time.
    Third-party plugins are discovered lazily from
    ``importlib.metadata.entry_points(group="rigger.{protocol}")``.
    """

    def __init__(self) -> None:
        self._builtins: dict[str, dict[str, type]] = {}
        self._plugins: dict[str, dict[str, type]] = {}
        self._plugins_loaded: set[str] = set()

    def register(self, protocol: str, name: str, cls: type) -> None:
        """Register a class under a protocol/name pair.

        Args:
            protocol: Protocol group name (e.g. ``"task_source"``).
            name: Config name (e.g. ``"file_list"``).
            cls: The implementation class.
        """
        self._builtins.setdefault(protocol, {})[name] = cls

    def get(self, protocol: str, name: str) -> type:
        """Look up a class by protocol and config name.

        Plugins override built-ins (with a warning logged on first load).

        Args:
            protocol: Protocol group name.
            name: Config name.

        Returns:
            The implementation class.

        Raises:
            KeyError: If no implementation is registered for the given
                protocol/name combination.
        """
        self._ensure_plugins_loaded(protocol)

        # Plugins take priority over built-ins.
        plugin_cls = self._plugins.get(protocol, {}).get(name)
        if plugin_cls is not None:
            return plugin_cls

        builtin_cls = self._builtins.get(protocol, {}).get(name)
        if builtin_cls is not None:
            return builtin_cls

        available = sorted(self._available_names(protocol))
        msg = (
            f"Unknown {protocol} type {name!r}. "
            f"Available: {', '.join(available) if available else '(none)'}"
        )
        raise KeyError(msg)

    def create(self, protocol: str, name: str, **kwargs: Any) -> Any:
        """Instantiate an implementation from config parameters.

        Args:
            protocol: Protocol group name.
            name: Config name.
            **kwargs: Constructor arguments forwarded to the class.

        Returns:
            An instance of the looked-up class.
        """
        cls = self.get(protocol, name)
        try:
            return cls(**kwargs)
        except TypeError as exc:
            msg = f"Failed to create {protocol}/{name} ({cls.__name__}): {exc}"
            raise TypeError(msg) from exc

    def available(self, protocol: str) -> list[str]:
        """Return sorted list of available config names for a protocol.

        Args:
            protocol: Protocol group name.

        Returns:
            Sorted list of registered config names.
        """
        self._ensure_plugins_loaded(protocol)
        return sorted(self._available_names(protocol))

    def _available_names(self, protocol: str) -> set[str]:
        names = set(self._builtins.get(protocol, {}).keys())
        names |= set(self._plugins.get(protocol, {}).keys())
        return names

    def _ensure_plugins_loaded(self, protocol: str) -> None:
        if protocol in self._plugins_loaded:
            return
        self._plugins_loaded.add(protocol)
        self._load_entry_points(protocol)

    def _load_entry_points(self, protocol: str) -> None:
        group = f"rigger.{protocol}"
        try:
            eps = importlib.metadata.entry_points(group=group)
        except TypeError:
            # Python <3.12 compat (shouldn't hit on 3.13+, but defensive).
            eps = importlib.metadata.entry_points().get(group, [])  # type: ignore[assignment]

        for ep in eps:
            try:
                cls = ep.load()
            except Exception:
                logger.warning(
                    "Failed to load entry point %s from group %s",
                    ep.name,
                    group,
                    exc_info=True,
                )
                continue

            if ep.name in self._builtins.get(protocol, {}):
                logger.warning(
                    "Plugin %r overrides built-in %s/%s",
                    ep.value,
                    protocol,
                    ep.name,
                )
            self._plugins.setdefault(protocol, {})[ep.name] = cls


def _build_default_registry() -> Registry:
    """Create a registry pre-populated with all built-in implementations."""
    # Lazy imports to avoid circular dependencies and speed up import
    # when the registry isn't used.
    from rigger.backends.claude_code import ClaudeCodeBackend
    from rigger.constraints import (
        BranchPolicyConstraint,
        ToolAllowlistConstraint,
    )
    from rigger.context_sources import (
        AgentsMdContextSource,
        FileTreeContextSource,
        McpCapabilityContextSource,
        StaticFilesContextSource,
    )
    from rigger.entropy_detectors import (
        DocStalenessEntropyDetector,
        ShellCommandEntropyDetector,
    )
    from rigger.state_stores import (
        HarnessDirStateStore,
        JsonFileStateStore,
    )
    from rigger.task_sources import (
        AtomicIssueTaskSource,
        FileListTaskSource,
        JsonStoriesTaskSource,
        LinearTaskSource,
    )
    from rigger.verifiers import (
        CiStatusVerifier,
        LintVerifier,
        RatchetVerifier,
        TestSuiteVerifier,
    )
    from rigger.workspace import (
        GitWorktreeManager,
        IndependentBranchManager,
        IndependentDirManager,
    )

    reg = Registry()

    # Task sources
    reg.register("task_source", "file_list", FileListTaskSource)
    reg.register("task_source", "linear", LinearTaskSource)
    reg.register("task_source", "atomic_issue", AtomicIssueTaskSource)
    reg.register("task_source", "json_stories", JsonStoriesTaskSource)

    # Context sources
    reg.register("context_source", "file_tree", FileTreeContextSource)
    reg.register("context_source", "agents_md", AgentsMdContextSource)
    reg.register("context_source", "mcp_capability", McpCapabilityContextSource)
    reg.register("context_source", "static_files", StaticFilesContextSource)

    # Verifiers
    reg.register("verifier", "test_suite", TestSuiteVerifier)
    reg.register("verifier", "lint", LintVerifier)
    reg.register("verifier", "ci_status", CiStatusVerifier)
    reg.register("verifier", "ratchet", RatchetVerifier)

    # Constraints
    reg.register("constraint", "tool_allowlist", ToolAllowlistConstraint)
    reg.register("constraint", "branch_policy", BranchPolicyConstraint)

    # State stores
    reg.register("state_store", "json_file", JsonFileStateStore)
    reg.register("state_store", "harness_dir", HarnessDirStateStore)

    # Entropy detectors
    reg.register("entropy_detector", "shell_command", ShellCommandEntropyDetector)
    reg.register("entropy_detector", "doc_staleness", DocStalenessEntropyDetector)

    # Workspace managers
    reg.register("workspace_manager", "git_worktree", GitWorktreeManager)
    reg.register("workspace_manager", "independent_dir", IndependentDirManager)
    reg.register("workspace_manager", "independent_branch", IndependentBranchManager)

    # Backends
    reg.register("backend", "claude_code", ClaudeCodeBackend)

    return reg


class _LazyRegistry:
    """Module-level singleton that defers built-in registration until first use."""

    def __init__(self) -> None:
        self._inner: Registry | None = None

    def _ensure(self) -> Registry:
        if self._inner is None:
            self._inner = _build_default_registry()
        return self._inner

    def register(self, protocol: str, name: str, cls: type) -> None:
        """Register a class under a protocol/name pair."""
        self._ensure().register(protocol, name, cls)

    def get(self, protocol: str, name: str) -> type:
        """Look up a class by protocol and config name."""
        return self._ensure().get(protocol, name)

    def create(self, protocol: str, name: str, **kwargs: Any) -> Any:
        """Instantiate an implementation from config parameters."""
        return self._ensure().create(protocol, name, **kwargs)

    def available(self, protocol: str) -> list[str]:
        """Return sorted list of available config names for a protocol."""
        return self._ensure().available(protocol)


registry: _LazyRegistry = _LazyRegistry()
"""Module-level registry singleton. Pre-populated with all built-in implementations."""
