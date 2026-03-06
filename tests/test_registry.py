"""Tests for the implementation registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rigger._registry import PROTOCOL_GROUPS, Registry, _build_default_registry

# ── Built-in lookup ────────────────────────────────────────────


class TestBuiltinLookup:
    """Verify all built-in implementations are discoverable by name."""

    @pytest.fixture
    def reg(self):
        return _build_default_registry()

    @pytest.mark.parametrize(
        ("protocol", "name"),
        [
            ("task_source", "file_list"),
            ("task_source", "linear"),
            ("task_source", "atomic_issue"),
            ("task_source", "json_stories"),
            ("context_source", "file_tree"),
            ("context_source", "agents_md"),
            ("context_source", "mcp_capability"),
            ("context_source", "static_files"),
            ("verifier", "test_suite"),
            ("verifier", "lint"),
            ("verifier", "ci_status"),
            ("verifier", "ratchet"),
            ("constraint", "tool_allowlist"),
            ("constraint", "branch_policy"),
            ("state_store", "json_file"),
            ("state_store", "harness_dir"),
            ("entropy_detector", "shell_command"),
            ("entropy_detector", "doc_staleness"),
            ("workspace_manager", "git_worktree"),
            ("workspace_manager", "independent_dir"),
            ("workspace_manager", "independent_branch"),
            ("backend", "claude_code"),
        ],
    )
    def test_builtin_lookup(self, reg, protocol, name):
        cls = reg.get(protocol, name)
        assert isinstance(cls, type)

    def test_all_protocols_have_at_least_one(self, reg):
        for protocol in PROTOCOL_GROUPS:
            names = reg.available(protocol)
            assert len(names) > 0, f"{protocol} has no registered implementations"


# ── Unknown type errors ────────────────────────────────────────


class TestUnknownType:
    @pytest.fixture
    def reg(self):
        return _build_default_registry()

    def test_unknown_name_raises_key_error(self, reg):
        with pytest.raises(KeyError, match="Unknown task_source type 'nonexistent'"):
            reg.get("task_source", "nonexistent")

    def test_error_lists_available(self, reg):
        with pytest.raises(KeyError, match="file_list"):
            reg.get("task_source", "nonexistent")

    def test_unknown_protocol_raises_key_error(self, reg):
        with pytest.raises(KeyError, match="Unknown bogus type 'foo'"):
            reg.get("bogus", "foo")

    def test_unknown_protocol_shows_none_available(self, reg):
        with pytest.raises(KeyError, match=r"\(none\)"):
            reg.get("bogus", "foo")


# ── Create with params ─────────────────────────────────────────


class TestCreate:
    def test_create_passes_kwargs(self):
        class FakeSource:
            def __init__(self, path, fmt="json"):
                self.path = path
                self.fmt = fmt

        reg = Registry()
        reg.register("task_source", "fake", FakeSource)
        instance = reg.create("task_source", "fake", path="tasks.json")

        assert isinstance(instance, FakeSource)
        assert instance.path == "tasks.json"
        assert instance.fmt == "json"

    def test_create_with_all_kwargs(self):
        class FakeSource:
            def __init__(self, path, fmt="json"):
                self.path = path
                self.fmt = fmt

        reg = Registry()
        reg.register("task_source", "fake", FakeSource)
        instance = reg.create("task_source", "fake", path="/x", fmt="yaml")

        assert instance.fmt == "yaml"

    def test_create_missing_required_param_raises_type_error(self):
        class FakeSource:
            def __init__(self, path):
                self.path = path

        reg = Registry()
        reg.register("task_source", "fake", FakeSource)

        with pytest.raises(TypeError, match="Failed to create task_source/fake"):
            reg.create("task_source", "fake")

    def test_create_unknown_type_raises_key_error(self):
        reg = Registry()
        with pytest.raises(KeyError):
            reg.create("task_source", "missing")


# ── Entry point discovery ──────────────────────────────────────


class TestEntryPoints:
    def test_entry_point_loaded(self):
        class PluginSource:
            pass

        ep = MagicMock()
        ep.name = "custom_source"
        ep.value = "my_plugin:PluginSource"
        ep.load.return_value = PluginSource

        reg = Registry()
        ep_patch = patch(
            "rigger._registry.importlib.metadata.entry_points",
            return_value=[ep],
        )
        with ep_patch:
            cls = reg.get("task_source", "custom_source")

        assert cls is PluginSource

    def test_plugin_overrides_builtin_with_warning(self):
        class BuiltinSource:
            pass

        class PluginSource:
            pass

        ep = MagicMock()
        ep.name = "file_list"
        ep.value = "my_plugin:PluginSource"
        ep.load.return_value = PluginSource

        reg = Registry()
        reg.register("task_source", "file_list", BuiltinSource)

        ep_patch = patch(
            "rigger._registry.importlib.metadata.entry_points",
            return_value=[ep],
        )
        with ep_patch, patch("rigger._registry.logger") as mock_logger:
            cls = reg.get("task_source", "file_list")

        assert cls is PluginSource
        mock_logger.warning.assert_called()

    def test_failed_entry_point_logged_and_skipped(self):
        ep = MagicMock()
        ep.name = "broken"
        ep.value = "bad_module:BadClass"
        ep.load.side_effect = ImportError("no such module")

        reg = Registry()
        ep_patch = patch(
            "rigger._registry.importlib.metadata.entry_points",
            return_value=[ep],
        )
        with (
            ep_patch,
            patch("rigger._registry.logger") as mock_logger,
            pytest.raises(KeyError),
        ):
            reg.get("task_source", "broken")

        mock_logger.warning.assert_called()

    def test_entry_points_loaded_once_per_protocol(self):
        reg = Registry()
        with patch(
            "rigger._registry.importlib.metadata.entry_points", return_value=[]
        ) as mock_eps:
            reg.available("task_source")
            reg.available("task_source")

        mock_eps.assert_called_once_with(group="rigger.task_source")


# ── Available ──────────────────────────────────────────────────


class TestAvailable:
    def test_available_returns_sorted(self):
        reg = Registry()
        reg.register("verifier", "zebra", type)
        reg.register("verifier", "alpha", type)

        with patch("rigger._registry.importlib.metadata.entry_points", return_value=[]):
            names = reg.available("verifier")

        assert names == ["alpha", "zebra"]


# ── Module-level singleton ─────────────────────────────────────


class TestSingleton:
    def test_registry_import(self):
        from rigger import registry

        # Should be able to call .get() on the singleton
        cls = registry.get("backend", "claude_code")
        assert isinstance(cls, type)

    def test_registry_available(self):
        from rigger import registry

        names = registry.available("task_source")
        assert "file_list" in names
        assert "linear" in names
