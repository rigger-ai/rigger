"""Tests for ClaudeCodeBackend."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rigger._types import EpochState, Task
from rigger.backends.claude_code import (
    ClaudeCodeBackend,
    DefaultPromptTemplates,
    PromptTemplateSet,
    _detect_changes,
    _snapshot_repo_state,
)

# ─── PromptTemplateSet ────────────────────────────────────────


class TestPromptTemplateSet:
    def test_render_initializer(self):
        templates = DefaultPromptTemplates()
        task = Task(id="task-1", description="Do something")
        state = EpochState(epoch=1)

        result = templates.render("initializer", task, state)

        assert "task-1" in result
        assert "epoch 1" in result

    def test_render_coding(self):
        templates = DefaultPromptTemplates()
        task = Task(id="task-2", description="Continue")
        state = EpochState(epoch=5, completed_tasks=["t1", "t2"])

        result = templates.render("coding", task, state)

        assert "task-2" in result
        assert "epoch 5" in result
        assert "2 tasks have been completed" in result

    def test_render_error_recovery(self):
        templates = DefaultPromptTemplates()
        task = Task(id="task-3", description="Recover")
        state = EpochState(epoch=3)

        result = templates.render("error_recovery", task, state)

        assert "task-3" in result
        assert "did not complete successfully" in result

    def test_custom_templates(self):
        custom = PromptTemplateSet(
            initializer="INIT: {task_id}",
            coding="CODE: {task_id} e{epoch}",
            error_recovery="ERR: {task_id}",
        )
        task = Task(id="x", description="test")
        state = EpochState(epoch=2)

        assert custom.render("initializer", task, state) == "INIT: x"
        assert custom.render("coding", task, state) == "CODE: x e2"
        assert custom.render("error_recovery", task, state) == "ERR: x"

    def test_default_templates_are_navigation_scripts(self):
        """Templates reference .harness/ paths, not file content (P1)."""
        templates = DefaultPromptTemplates()

        assert ".harness/current_task.json" in templates.initializer
        assert ".harness/current_task.json" in templates.coding
        assert ".harness/current_task.json" in templates.error_recovery
        assert ".harness/state.json" in templates.coding
        assert "AGENTS.md" in templates.initializer

    def test_coding_template_has_fresh_context_warning(self):
        """Explicit warning about fresh context (C9 pattern)."""
        templates = DefaultPromptTemplates()
        assert "FRESH context window" in templates.coding
        assert "FRESH context window" in templates.error_recovery


# ─── _determine_phase ────────────────────────────────────────


class TestDeterminePhase:
    def setup_method(self):
        self.backend = ClaudeCodeBackend()

    def test_epoch_0_is_initializer(self):
        state = EpochState(epoch=0)
        assert self.backend._determine_phase(state) == "initializer"

    def test_epoch_1_is_initializer(self):
        state = EpochState(epoch=1)
        assert self.backend._determine_phase(state) == "initializer"

    def test_epoch_2_no_failure_is_coding(self):
        state = EpochState(epoch=2)
        assert self.backend._determine_phase(state) == "coding"

    def test_epoch_3_with_failure_is_error_recovery(self):
        state = EpochState(epoch=3, metadata={"last_result_status": "failure"})
        assert self.backend._determine_phase(state) == "error_recovery"

    def test_epoch_3_with_error_is_error_recovery(self):
        state = EpochState(epoch=3, metadata={"last_result_status": "error"})
        assert self.backend._determine_phase(state) == "error_recovery"

    def test_epoch_3_with_success_is_coding(self):
        state = EpochState(epoch=3, metadata={"last_result_status": "success"})
        assert self.backend._determine_phase(state) == "coding"

    def test_epoch_3_with_partial_is_coding(self):
        state = EpochState(epoch=3, metadata={"last_result_status": "partial"})
        assert self.backend._determine_phase(state) == "coding"


# ─── _build_sdk_options ──────────────────────────────────────


class TestBuildSdkOptions:
    def setup_method(self):
        self.backend = ClaudeCodeBackend()

    def test_base_options(self):
        opts = self.backend._build_sdk_options(Path("/proj"), {})

        assert opts["cwd"] == "/proj"
        assert opts["model"] == "claude-sonnet-4-6"
        assert opts["setting_sources"] == ["project"]
        assert opts["permission_mode"] == "bypassPermissions"

    def test_setting_sources_always_project(self):
        """setting_sources=["project"] is hardcoded (Task 5.4 D3)."""
        opts = self.backend._build_sdk_options(Path("/proj"), {})
        assert opts["setting_sources"] == ["project"]

    def test_no_tool_restrictions_when_empty(self):
        opts = self.backend._build_sdk_options(Path("/p"), {})

        assert "allowed_tools" not in opts
        assert "disallowed_tools" not in opts
        assert "max_turns" not in opts

    def test_disallowed_tools_additive_merge(self):
        backend = ClaudeCodeBackend(disallowed_tools=["Bash"])
        constraints = {"disallowed_tools": ["Write"]}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert sorted(opts["disallowed_tools"]) == ["Bash", "Write"]

    def test_allowed_tools_restrictive_merge(self):
        backend = ClaudeCodeBackend(allowed_tools=["Read", "Bash", "Write"])
        constraints = {"allowed_tools": ["Read", "Write"]}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert sorted(opts["allowed_tools"]) == ["Read", "Write"]

    def test_allowed_tools_no_constructor_restriction(self):
        """When constructor has no allowed_tools, file sets the allowlist."""
        backend = ClaudeCodeBackend()
        constraints = {"allowed_tools": ["Read", "Write"]}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert sorted(opts["allowed_tools"]) == ["Read", "Write"]

    def test_max_turns_scalar_min_file_wins(self):
        backend = ClaudeCodeBackend(max_turns=100)
        constraints = {"max_iterations": 50}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert opts["max_turns"] == 50

    def test_max_turns_scalar_min_constructor_wins(self):
        backend = ClaudeCodeBackend(max_turns=30)
        constraints = {"max_iterations": 50}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert opts["max_turns"] == 30

    def test_max_turns_file_only(self):
        backend = ClaudeCodeBackend()
        constraints = {"max_iterations": 75}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert opts["max_turns"] == 75

    def test_constructor_disallowed_cannot_be_loosened(self):
        """Constructor restrictions are the FLOOR (Task 5.4 §3.2)."""
        backend = ClaudeCodeBackend(disallowed_tools=["Bash", "Write"])
        # Constraints only add, never remove
        constraints = {"disallowed_tools": ["Edit"]}

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert "Bash" in opts["disallowed_tools"]
        assert "Write" in opts["disallowed_tools"]
        assert "Edit" in opts["disallowed_tools"]

    def test_optional_params_passed_through(self):
        backend = ClaudeCodeBackend(
            system_prompt="test prompt",
            mcp_servers={"server": {}},
            hooks={"PreToolUse": []},
            sandbox={"mode": "strict"},
            env={"API_KEY": "val"},
            add_dirs=["/extra"],
        )

        opts = backend._build_sdk_options(Path("/p"), {})

        assert opts["system_prompt"] == "test prompt"
        assert opts["mcp_servers"] == {"server": {}}
        assert opts["hooks"] == {"PreToolUse": []}
        assert opts["sandbox"] == {"mode": "strict"}
        assert opts["env"] == {"API_KEY": "val"}
        assert opts["add_dirs"] == ["/extra"]

    def test_combined_constraints(self):
        """All three merge families applied together."""
        backend = ClaudeCodeBackend(
            allowed_tools=["Read", "Write", "Bash"],
            disallowed_tools=["Edit"],
            max_turns=100,
        )
        constraints = {
            "allowed_tools": ["Read", "Write"],
            "disallowed_tools": ["Glob"],
            "max_iterations": 50,
        }

        opts = backend._build_sdk_options(Path("/p"), constraints)

        assert sorted(opts["allowed_tools"]) == ["Read", "Write"]
        assert sorted(opts["disallowed_tools"]) == ["Edit", "Glob"]
        assert opts["max_turns"] == 50


# ─── _parse_result ───────────────────────────────────────────


class TestParseResult:
    def setup_method(self):
        self.backend = ClaudeCodeBackend()

    def test_success_on_new_commits(self):
        changes = {
            "new_commits": ["abc123"],
            "modified_files": ["foo.py"],
            "has_uncommitted_changes": False,
        }

        result = self.backend._parse_result("t1", "done", changes, 10.0)

        assert result.status == "success"
        assert result.task_id == "t1"
        assert result.commits == ["abc123"]
        assert result.artifacts == [Path("foo.py")]
        assert result.metadata["commit_count"] == 1

    def test_partial_on_modified_files_no_commits(self):
        changes = {
            "new_commits": [],
            "modified_files": ["bar.py"],
            "has_uncommitted_changes": False,
        }

        result = self.backend._parse_result("t1", "", changes, 5.0)

        assert result.status == "partial"

    def test_partial_on_uncommitted_changes(self):
        changes = {
            "new_commits": [],
            "modified_files": [],
            "has_uncommitted_changes": True,
        }

        result = self.backend._parse_result("t1", "", changes, 5.0)

        assert result.status == "partial"

    def test_failure_on_no_changes(self):
        changes = {
            "new_commits": [],
            "modified_files": [],
            "has_uncommitted_changes": False,
        }

        result = self.backend._parse_result("t1", "", changes, 5.0)

        assert result.status == "failure"

    def test_metadata_fields(self):
        changes = {
            "new_commits": ["a", "b"],
            "modified_files": ["x.py", "y.py", "z.py"],
            "has_uncommitted_changes": True,
        }

        result = self.backend._parse_result("t1", "hello", changes, 42.0)

        assert result.metadata["execution_time_s"] == 42.0
        assert result.metadata["agent_output_length"] == 5
        assert result.metadata["commit_count"] == 2
        assert result.metadata["files_changed"] == 3
        assert result.metadata["has_uncommitted_changes"] is True


# ─── _snapshot_repo_state ────────────────────────────────────


class TestSnapshotRepoState:
    @patch("rigger.backends.claude_code.subprocess.run")
    def test_captures_head_and_dirty(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd[1] == "rev-parse":
                return MagicMock(returncode=0, stdout="abc123\n")
            if cmd[1] == "status":
                return MagicMock(returncode=0, stdout=" M file.py\n?? new.py\n")
            return MagicMock(returncode=1)

        mock_run.side_effect = side_effect

        snapshot = _snapshot_repo_state(Path("/proj"))

        assert snapshot["head"] == "abc123"
        assert "file.py" in snapshot["dirty_files"]
        assert "new.py" in snapshot["dirty_files"]

    @patch("rigger.backends.claude_code.subprocess.run")
    def test_handles_no_git(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        snapshot = _snapshot_repo_state(Path("/proj"))

        assert snapshot["head"] is None
        assert snapshot["dirty_files"] == []

    @patch("rigger.backends.claude_code.subprocess.run")
    def test_handles_not_a_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")

        snapshot = _snapshot_repo_state(Path("/proj"))

        assert snapshot["head"] is None
        assert snapshot["dirty_files"] == []


# ─── _detect_changes ─────────────────────────────────────────


class TestDetectChanges:
    @patch("rigger.backends.claude_code.subprocess.run")
    def test_detects_new_commits(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "log" in cmd:
                return MagicMock(returncode=0, stdout="def456\nabc123\n")
            if "diff" in cmd:
                return MagicMock(returncode=0, stdout="changed.py\n")
            return MagicMock(returncode=1)

        mock_run.side_effect = side_effect

        pre = {"head": "abc000", "dirty_files": []}
        post = {"head": "def456", "dirty_files": []}
        changes = _detect_changes(pre, post, Path("/proj"))

        assert changes["new_commits"] == ["def456", "abc123"]
        assert changes["modified_files"] == ["changed.py"]

    def test_no_changes_same_head(self):
        pre = {"head": "abc123", "dirty_files": []}
        post = {"head": "abc123", "dirty_files": []}

        changes = _detect_changes(pre, post, Path("/proj"))

        assert changes["new_commits"] == []
        assert not changes["has_uncommitted_changes"]

    def test_detects_uncommitted_changes(self):
        pre = {"head": "abc123", "dirty_files": []}
        post = {"head": "abc123", "dirty_files": ["new.py"]}

        changes = _detect_changes(pre, post, Path("/proj"))

        assert changes["has_uncommitted_changes"] is True

    def test_preexisting_dirty_files_not_counted(self):
        """Only NEW dirty files trigger has_uncommitted_changes."""
        pre = {"head": "abc123", "dirty_files": ["old.py"]}
        post = {"head": "abc123", "dirty_files": ["old.py"]}

        changes = _detect_changes(pre, post, Path("/proj"))

        assert changes["has_uncommitted_changes"] is False

    def test_no_head_means_no_commits_or_files(self):
        pre = {"head": None, "dirty_files": []}
        post = {"head": None, "dirty_files": []}

        changes = _detect_changes(pre, post, Path("/proj"))

        assert changes["new_commits"] == []
        assert changes["modified_files"] == []

    @patch("rigger.backends.claude_code.subprocess.run")
    def test_git_log_failure_falls_back_to_post_head(self, mock_run):
        """If git log fails, at least record that HEAD moved."""
        mock_run.side_effect = FileNotFoundError()

        pre = {"head": "old", "dirty_files": []}
        post = {"head": "new", "dirty_files": []}
        changes = _detect_changes(pre, post, Path("/proj"))

        assert changes["new_commits"] == ["new"]


# ─── Constructor ──────────────────────────────────────────────


class TestConstructor:
    def test_defaults(self):
        backend = ClaudeCodeBackend()

        assert backend.model == "claude-sonnet-4-6"
        assert backend.system_prompt is None
        assert backend.permission_mode == "bypassPermissions"
        assert backend.mcp_servers == {}
        assert backend.allowed_tools == []
        assert backend.disallowed_tools == []
        assert backend.max_turns is None
        assert backend.hooks is None
        assert backend.sandbox is None
        assert backend.env == {}
        assert backend.add_dirs == []
        assert isinstance(backend.templates, PromptTemplateSet)

    def test_custom_model(self):
        backend = ClaudeCodeBackend(model="claude-opus-4-6")
        assert backend.model == "claude-opus-4-6"

    def test_add_dirs_converted_to_strings(self):
        backend = ClaudeCodeBackend(add_dirs=[Path("/a"), "/b"])
        assert backend.add_dirs == ["/a", "/b"]

    def test_custom_templates(self):
        custom = PromptTemplateSet(initializer="a", coding="b", error_recovery="c")
        backend = ClaudeCodeBackend(prompt_templates=custom)
        assert backend.templates is custom


# ─── execute() integration ───────────────────────────────────


class TestExecute:
    @pytest.fixture
    def backend(self):
        return ClaudeCodeBackend()

    @patch("rigger.backends.claude_code.read_current_task", return_value=None)
    @patch(
        "rigger.backends.claude_code.read_state",
        return_value=EpochState(epoch=1),
    )
    @patch("rigger.backends.claude_code.read_constraints", return_value={})
    async def test_missing_task_returns_error(
        self, _mock_constraints, _mock_state, _mock_task, backend
    ):
        result = await backend.execute(Path("/proj"))

        assert result.status == "error"
        assert result.task_id == "unknown"
        assert result.metadata["error"] == "missing_current_task"

    @patch("rigger.backends.claude_code._detect_changes")
    @patch("rigger.backends.claude_code._snapshot_repo_state")
    @patch("rigger.backends.claude_code.read_constraints", return_value={})
    @patch(
        "rigger.backends.claude_code.read_state",
        return_value=EpochState(epoch=1),
    )
    @patch("rigger.backends.claude_code.read_current_task")
    async def test_successful_execution(
        self,
        mock_task,
        _mock_state,
        _mock_constraints,
        mock_snapshot,
        mock_changes,
        backend,
    ):
        mock_task.return_value = Task(id="t1", description="test")
        mock_snapshot.return_value = {"head": "abc", "dirty_files": []}
        mock_changes.return_value = {
            "new_commits": ["def"],
            "modified_files": ["x.py"],
            "has_uncommitted_changes": False,
        }

        with patch.object(backend, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "done"
            result = await backend.execute(Path("/proj"))

        assert result.status == "success"
        assert result.task_id == "t1"
        assert result.commits == ["def"]
        assert result.artifacts == [Path("x.py")]

    @patch("rigger.backends.claude_code._detect_changes")
    @patch("rigger.backends.claude_code._snapshot_repo_state")
    @patch("rigger.backends.claude_code.read_constraints", return_value={})
    @patch(
        "rigger.backends.claude_code.read_state",
        return_value=EpochState(epoch=1),
    )
    @patch("rigger.backends.claude_code.read_current_task")
    async def test_execution_exception_returns_error(
        self,
        mock_task,
        _mock_state,
        _mock_constraints,
        mock_snapshot,
        mock_changes,
        backend,
    ):
        mock_task.return_value = Task(id="t1", description="test")
        mock_snapshot.return_value = {"head": "abc", "dirty_files": []}
        mock_changes.return_value = {
            "new_commits": [],
            "modified_files": ["partial.py"],
            "has_uncommitted_changes": False,
        }

        with patch.object(backend, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("SDK error")
            result = await backend.execute(Path("/proj"))

        assert result.status == "error"
        assert result.task_id == "t1"
        assert "SDK error" in result.metadata["error"]
        assert result.metadata["error_type"] == "RuntimeError"
        assert result.artifacts == [Path("partial.py")]

    @patch("rigger.backends.claude_code._detect_changes")
    @patch("rigger.backends.claude_code._snapshot_repo_state")
    @patch("rigger.backends.claude_code.read_constraints", return_value={})
    @patch(
        "rigger.backends.claude_code.read_state",
        return_value=EpochState(epoch=1),
    )
    @patch("rigger.backends.claude_code.read_current_task")
    async def test_no_changes_returns_failure(
        self,
        mock_task,
        _mock_state,
        _mock_constraints,
        mock_snapshot,
        mock_changes,
        backend,
    ):
        mock_task.return_value = Task(id="t1", description="test")
        mock_snapshot.return_value = {"head": "abc", "dirty_files": []}
        mock_changes.return_value = {
            "new_commits": [],
            "modified_files": [],
            "has_uncommitted_changes": False,
        }

        with patch.object(backend, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""
            result = await backend.execute(Path("/proj"))

        assert result.status == "failure"

    @patch("rigger.backends.claude_code._detect_changes")
    @patch("rigger.backends.claude_code._snapshot_repo_state")
    @patch("rigger.backends.claude_code.read_constraints", return_value={})
    @patch(
        "rigger.backends.claude_code.read_state",
        return_value=EpochState(epoch=5, completed_tasks=["a", "b"]),
    )
    @patch("rigger.backends.claude_code.read_current_task")
    async def test_epoch_5_uses_coding_template(
        self,
        mock_task,
        _mock_state,
        _mock_constraints,
        mock_snapshot,
        mock_changes,
        backend,
    ):
        mock_task.return_value = Task(id="t1", description="test")
        mock_snapshot.return_value = {"head": "abc", "dirty_files": []}
        mock_changes.return_value = {
            "new_commits": ["x"],
            "modified_files": [],
            "has_uncommitted_changes": False,
        }

        with patch.object(backend, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""
            await backend.execute(Path("/proj"))

        # Verify the prompt contains coding template markers
        prompt_arg = mock_run.call_args[0][1]
        assert "FRESH context window" in prompt_arg
        assert "2 tasks have been completed" in prompt_arg

    @patch("rigger.backends.claude_code._detect_changes")
    @patch("rigger.backends.claude_code._snapshot_repo_state")
    @patch(
        "rigger.backends.claude_code.read_constraints",
        return_value={"disallowed_tools": ["Bash"]},
    )
    @patch(
        "rigger.backends.claude_code.read_state",
        return_value=EpochState(epoch=1),
    )
    @patch("rigger.backends.claude_code.read_current_task")
    async def test_constraints_merged_into_sdk_options(
        self,
        mock_task,
        _mock_state,
        _mock_constraints,
        mock_snapshot,
        mock_changes,
        backend,
    ):
        mock_task.return_value = Task(id="t1", description="test")
        mock_snapshot.return_value = {"head": "abc", "dirty_files": []}
        mock_changes.return_value = {
            "new_commits": [],
            "modified_files": [],
            "has_uncommitted_changes": False,
        }

        with patch.object(backend, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""
            await backend.execute(Path("/proj"))

        sdk_options = mock_run.call_args[0][0]
        assert "Bash" in sdk_options["disallowed_tools"]
