"""ClaudeCodeBackend — AgentBackend implementation using the Claude Agent SDK.

The first concrete AgentBackend for Rigger. Wraps the Claude Agent SDK
to execute a coding agent inside ``execute(project_root)``. Per-epoch
fresh client creation, defense-in-depth constraints merge, and git-based
result parsing.

Source: Task 5.4 (ClaudeCodeBackend Reference Implementation Design),
Task 5.9 (setting_sources Backend Convention).
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rigger._schema import read_constraints, read_current_task, read_state
from rigger._types import EpochState, Task, TaskResult

logger = logging.getLogger(__name__)

# ─── Prompt Templates ──────────────────────────────────────────

INITIALIZER_TEMPLATE = """\
You are a coding agent starting a NEW project session. This is the initial \
setup phase (epoch {epoch}).

## STEP 1: ORIENT YOURSELF (MANDATORY)

Before doing anything else, read these files to understand the project:

1. Read `AGENTS.md` in the project root — this is your navigation map
2. Read `.harness/current_task.json` — this is your assignment
3. Run `ls -la` to see the project structure
4. Run `git log --oneline -5` to see recent history (if any)

## STEP 2: UNDERSTAND YOUR TASK

Your current task ID is: {task_id}

Read `.harness/current_task.json` for the full task description and metadata. \
The task description contains everything you need to know about what to build.

## STEP 3: SET UP THE ENVIRONMENT

Since this is the first session:
1. Ensure the development environment is properly configured
2. Install any necessary dependencies
3. Create initial project structure if needed
4. Make an initial commit with your setup changes

## STEP 4: BEGIN IMPLEMENTATION

Start working on the task described in `.harness/current_task.json`. \
Make incremental commits as you progress.

## STEP 5: LEAVE A CLEAN STATE

Before finishing:
1. Ensure all changes are committed with descriptive messages
2. Run any available tests
3. Leave the working tree clean (no uncommitted changes)
"""

CODING_TEMPLATE = """\
You are a coding agent continuing work on a development project. This is \
epoch {epoch} — {completed_count} tasks have been completed before this session.

IMPORTANT: This is a FRESH context window. You have NO memory of previous \
sessions. All continuity comes from the filesystem and git history.

## STEP 1: ORIENT YOURSELF (MANDATORY)

Read these files IN ORDER to understand where you are:

1. `AGENTS.md` — project conventions and navigation map
2. `.harness/state.json` — epoch count, completed/pending tasks
3. `.harness/current_task.json` — your current assignment
4. `git log --oneline -20` — what happened in recent sessions
5. `git diff HEAD~3 --stat` — what changed recently

## STEP 2: UNDERSTAND THE CURRENT TASK

Your current task ID is: {task_id}

Read `.harness/current_task.json` for the complete task specification. \
This file contains the full description and any metadata.

## STEP 3: REVIEW RELEVANT CONTEXT

Based on the task and AGENTS.md, read any relevant source files, \
documentation, or test files before making changes.

## STEP 4: IMPLEMENT

Work on the task described in `.harness/current_task.json`:
1. Make focused, incremental changes
2. Commit each logical change separately with descriptive messages
3. Run tests after each significant change
4. If tests fail, fix the issue before moving on

## STEP 5: VERIFY AND COMMIT

Before finishing:
1. Run the full test suite
2. Ensure all changes are committed
3. Leave the working tree clean
4. If you completed the task, ensure your commits clearly reflect this
"""

ERROR_RECOVERY_TEMPLATE = """\
You are a coding agent continuing work on a development project. This is \
epoch {epoch}. The PREVIOUS session encountered an issue.

IMPORTANT: This is a FRESH context window. You have NO memory of the \
previous session or its errors.

## STEP 1: ORIENT YOURSELF (MANDATORY)

Read these files IN ORDER:

1. `AGENTS.md` — project conventions and navigation map
2. `.harness/state.json` — epoch count, completed/pending tasks
3. `.harness/current_task.json` — your current assignment (same task as before)
4. `git log --oneline -20` — see what the previous session did (if anything)
5. `git status` — check for uncommitted changes from the failed session
6. `git diff` — review any uncommitted work

## STEP 2: ASSESS THE SITUATION

The previous session working on task {task_id} did not complete successfully.

Examine the repository state:
1. Check git log for any partial commits from the last session
2. Look for uncommitted changes that may contain partial work
3. Check if tests are currently passing or failing
4. Review any error messages in test output

## STEP 3: RECOVER AND CONTINUE

Based on your assessment:
- If there are useful partial changes, build on them
- If the previous changes are broken, revert them and start fresh
- If tests are failing, fix them before adding new functionality

## STEP 4: IMPLEMENT THE TASK

Continue working on the task from `.harness/current_task.json`. \
Apply any lessons from the failed attempt.

## STEP 5: VERIFY AND COMMIT

Before finishing:
1. Run the full test suite
2. Ensure all changes are committed with descriptive messages
3. Leave the working tree clean
"""


@dataclass
class PromptTemplateSet:
    """A set of prompt templates for different execution phases.

    Templates use ``str.format()`` placeholders:
        ``{task_id}``: Current task ID.
        ``{epoch}``: Current epoch number.
        ``{completed_count}``: Number of completed tasks.
        ``{pending_count}``: Number of pending tasks.
        ``{error_context}``: Error info from prior epoch (error_recovery only).

    Default templates reference ``.harness/`` files by path (Navigation Script
    pattern P1), not by content injection. Custom subclasses may override
    ``render()`` to inject additional variables.

    Source: Task 5.4 §2, Task 1.11 Pattern 1 (Navigation Script).
    """

    initializer: str
    coding: str
    error_recovery: str

    def render(
        self,
        phase: str,
        task: Task,
        state: EpochState,
    ) -> str:
        """Render the template for the given phase.

        Args:
            phase: One of "initializer", "coding", "error_recovery".
            task: Current task from .harness/current_task.json.
            state: Current epoch state from .harness/state.json.

        Returns:
            Rendered prompt string.
        """
        template = getattr(self, phase)
        error_context = state.metadata.get("last_error", "")

        return template.format(
            task_id=task.id,
            epoch=state.epoch,
            completed_count=len(state.completed_tasks),
            pending_count=len(state.pending_tasks),
            error_context=error_context,
        )


def DefaultPromptTemplates() -> PromptTemplateSet:
    """Factory for the default prompt template set.

    Source: Task 5.4 §2.5.
    """
    return PromptTemplateSet(
        initializer=INITIALIZER_TEMPLATE,
        coding=CODING_TEMPLATE,
        error_recovery=ERROR_RECOVERY_TEMPLATE,
    )


# ─── Git Helpers ────────────────────────────────────────────────


def _snapshot_repo_state(project_root: Path) -> dict[str, Any]:
    """Capture pre/post-execution repository state for change detection.

    Source: Task 5.4 §1.2.

    Args:
        project_root: Root of the project.

    Returns:
        Dict with ``head`` (commit hash or None) and ``dirty_files`` (list).
    """
    snapshot: dict[str, Any] = {"head": None, "dirty_files": []}

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            snapshot["head"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            snapshot["dirty_files"] = [
                line[3:] for line in result.stdout.splitlines() if line.strip()
            ]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return snapshot


def _detect_changes(
    pre: dict[str, Any],
    post: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Compare pre- and post-execution snapshots to find changes.

    Source: Task 5.4 §1.2, cross-examination X2 (cwd parameter).

    Args:
        pre: Pre-execution snapshot from ``_snapshot_repo_state()``.
        post: Post-execution snapshot from ``_snapshot_repo_state()``.
        project_root: Project directory for git commands.

    Returns:
        Dict with ``new_commits``, ``modified_files``, and
        ``has_uncommitted_changes``.
    """
    changes: dict[str, Any] = {
        "new_commits": [],
        "modified_files": [],
        "has_uncommitted_changes": False,
    }

    pre_head = pre.get("head")
    post_head = post.get("head")

    # Detect new commits
    if pre_head and post_head and pre_head != post_head:
        try:
            result = subprocess.run(
                ["git", "log", "--format=%H", f"{pre_head}..{post_head}"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                changes["new_commits"] = [
                    h for h in result.stdout.strip().splitlines() if h
                ]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # If git log fails, at least record that HEAD moved
            changes["new_commits"] = [post_head]

    # Detect modified files (diff between pre-head and current state)
    if pre_head:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", pre_head],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                changes["modified_files"] = [
                    f for f in result.stdout.strip().splitlines() if f
                ]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Detect uncommitted changes (new dirty files since pre-execution)
    post_dirty = set(post.get("dirty_files", []))
    pre_dirty = set(pre.get("dirty_files", []))
    if post_dirty - pre_dirty:
        changes["has_uncommitted_changes"] = True

    return changes


# ─── ClaudeCodeBackend ──────────────────────────────────────────


class ClaudeCodeBackend:
    """AgentBackend implementation for the Claude Agent SDK.

    Wraps the Claude Agent SDK to execute a coding agent in a fresh context
    per epoch. Prompt construction, SDK configuration, and result parsing
    are entirely internal to this class.

    The agent is a BLACK BOX. This backend:

    - READS ``.harness/`` files written by the Rigger loop
    - CONSTRUCTS prompt templates from ``.harness/`` data
    - CONFIGURES the SDK client (setting_sources, tools, permissions)
    - EXECUTES the agent via the SDK
    - PARSES observable side effects into TaskResult

    It MUST NOT:

    - Write to ``.harness/`` (Rigger-owned)
    - Model agent-internal decision-making
    - Pass context via any channel other than filesystem + SDK config

    Required convention: ``setting_sources=["project"]`` is hardcoded for
    filesystem-provisioned context (AGENTS.md, CLAUDE.md) to be loaded
    by the agent. (Task 5.4 D3, Task 5.9).

    Source: Task 5.4, Task 5.9.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        system_prompt: str | None = None,
        permission_mode: str = "bypassPermissions",
        mcp_servers: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        max_turns: int | None = None,
        hooks: dict[str, Any] | None = None,
        sandbox: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
        add_dirs: list[str | Path] | None = None,
        prompt_templates: PromptTemplateSet | None = None,
    ) -> None:
        """Initialize the ClaudeCodeBackend.

        All parameters are STATIC backend configuration (Task 1.17 §4.1).
        Dynamic per-epoch configuration flows through
        ``.harness/constraints.json``.

        Args:
            model: Claude model to use.
            system_prompt: Optional system prompt override. Most harnesses
                should leave this None and use CLAUDE.md/AGENTS.md via
                setting_sources instead.
            permission_mode: Tool permission mode for automated execution.
            mcp_servers: MCP server configurations. Static for MVP.
            allowed_tools: Constructor-level tool allowlist (the FLOOR).
            disallowed_tools: Constructor-level tool denylist.
            max_turns: Constructor-level turn limit.
            hooks: SDK lifecycle hooks.
            sandbox: Sandbox configuration.
            env: Environment variables for the agent subprocess.
            add_dirs: Additional directories the agent can access.
            prompt_templates: Custom prompt template set. Defaults to
                the built-in templates shipped with this backend.
        """
        self.model = model
        self.system_prompt = system_prompt
        self.permission_mode = permission_mode
        self.mcp_servers = mcp_servers or {}
        self.allowed_tools = list(allowed_tools or [])
        self.disallowed_tools = list(disallowed_tools or [])
        self.max_turns = max_turns
        self.hooks = hooks
        self.sandbox = sandbox
        self.env = env or {}
        self.add_dirs = [str(d) for d in (add_dirs or [])]
        self.templates = prompt_templates or DefaultPromptTemplates()

    async def execute(self, project_root: Path) -> TaskResult:
        """Execute a coding agent in a fresh context.

        Implements the ``AgentBackend`` protocol. Sequence (Task 5.4 §1.2):

        1. Read .harness/ files (task, state, constraints)
        2. Determine prompt phase (initializer / coding / error_recovery)
        3. Build SDK options (merge constructor + constraints)
        4. Snapshot pre-execution git state
        5. Build prompt and execute agent
        6. Diff git state to detect changes
        7. Parse and return TaskResult

        Args:
            project_root: The project directory.

        Returns:
            TaskResult with observable side effects.
        """
        start_time = time.monotonic()

        # ── Step 1: Read .harness/ files ──
        task = read_current_task(project_root)
        state = read_state(project_root)
        constraints = read_constraints(project_root)

        # Handle missing MUST file: current_task.json (Task 5.4 §5)
        if task is None:
            logger.error(
                "Cannot execute: .harness/current_task.json is missing or malformed"
            )
            return TaskResult(
                task_id="unknown",
                status="error",
                metadata={
                    "error": "missing_current_task",
                    "error_type": "MissingTaskFile",
                    "execution_time_s": time.monotonic() - start_time,
                },
            )

        # ── Step 2: Determine prompt phase ──
        phase = self._determine_phase(state)

        # ── Step 3: Build SDK options ──
        sdk_options = self._build_sdk_options(project_root, constraints)

        # ── Step 4: Snapshot pre-execution state ──
        pre_snapshot = _snapshot_repo_state(project_root)

        # ── Step 5: Build prompt and execute ──
        prompt = self.templates.render(phase=phase, task=task, state=state)

        try:
            agent_output = await self._run_agent(sdk_options, prompt)
        except Exception as exc:
            logger.error("Agent execution failed: %s", exc)
            post_snapshot = _snapshot_repo_state(project_root)
            changes = _detect_changes(pre_snapshot, post_snapshot, project_root)
            return TaskResult(
                task_id=task.id,
                status="error",
                artifacts=[Path(f) for f in changes["modified_files"]],
                commits=changes["new_commits"],
                metadata={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "execution_time_s": time.monotonic() - start_time,
                    "partial_changes": bool(changes["new_commits"]),
                },
            )

        # ── Step 6: Detect changes ──
        post_snapshot = _snapshot_repo_state(project_root)
        changes = _detect_changes(pre_snapshot, post_snapshot, project_root)

        # ── Step 7: Parse and return TaskResult ──
        return self._parse_result(
            task_id=task.id,
            agent_output=agent_output,
            changes=changes,
            execution_time_s=time.monotonic() - start_time,
        )

    def _determine_phase(self, state: EpochState) -> str:
        """Determine which prompt template to use.

        Two-Phase Startup (P2) + error recovery (Task 5.4 D7, D12):

        - epoch <= 1 -> "initializer"
        - epoch > 1 with prior failure/error -> "error_recovery"
        - epoch > 1 -> "coding"

        Args:
            state: Current epoch state.

        Returns:
            Phase name: "initializer", "coding", or "error_recovery".
        """
        if state.epoch <= 1:
            return "initializer"

        last_status = state.metadata.get("last_result_status")
        if last_status in ("error", "failure"):
            return "error_recovery"

        return "coding"

    def _build_sdk_options(
        self,
        project_root: Path,
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """Build SDK client options from constructor + constraints.

        Defense-in-depth merge (Task 5.4 §3.2, Task 1.17 §2.2):
        Constructor restrictions are the FLOOR. ``.harness/constraints.json``
        can only tighten, never loosen.

        Args:
            project_root: Project directory (becomes ``cwd``).
            constraints: Parsed constraints from ``.harness/constraints.json``.

        Returns:
            Dict of options for ``ClaudeAgentOptions`` construction.
        """
        options: dict[str, Any] = {
            "cwd": str(project_root),
            "model": self.model,
            "setting_sources": ["project"],  # REQUIRED (Task 5.4 D3)
            "permission_mode": self.permission_mode,
        }

        # Optional constructor parameters
        if self.system_prompt:
            options["system_prompt"] = self.system_prompt
        if self.mcp_servers:
            options["mcp_servers"] = self.mcp_servers
        if self.hooks:
            options["hooks"] = self.hooks
        if self.sandbox:
            options["sandbox"] = self.sandbox
        if self.env:
            options["env"] = self.env
        if self.add_dirs:
            options["add_dirs"] = self.add_dirs

        # ── Defense-in-depth merge ──
        effective_allowed = set(self.allowed_tools) if self.allowed_tools else None
        effective_disallowed = set(self.disallowed_tools)
        effective_max_turns = self.max_turns

        if constraints:
            # disallowed_tools: ADDITIVE (union) — can only grow
            file_disallowed = constraints.get("disallowed_tools", [])
            effective_disallowed.update(file_disallowed)

            # allowed_tools: RESTRICTIVE (intersection) — can only shrink
            file_allowed = constraints.get("allowed_tools", [])
            if file_allowed:
                file_set = set(file_allowed)
                if effective_allowed is not None:
                    effective_allowed = effective_allowed & file_set
                else:
                    effective_allowed = file_set

            # max_iterations -> max_turns: SCALAR-MIN — can only decrease
            file_max = constraints.get("max_iterations")
            if file_max is not None:
                if effective_max_turns is not None:
                    effective_max_turns = min(effective_max_turns, file_max)
                else:
                    effective_max_turns = file_max

        # Apply merged restrictions
        if effective_allowed is not None:
            options["allowed_tools"] = sorted(effective_allowed)
        if effective_disallowed:
            options["disallowed_tools"] = sorted(effective_disallowed)
        if effective_max_turns is not None:
            options["max_turns"] = effective_max_turns

        return options

    async def _run_agent(
        self,
        sdk_options: dict[str, Any],
        prompt: str,
    ) -> str:
        """Create a fresh SDK client and execute the prompt.

        Single SDK coupling point (Task 5.4 D9). Per-epoch fresh client
        creation (C1, C9 patterns). Uses the standalone ``query()`` function
        for one-shot execution.

        Args:
            sdk_options: Options dict for ``ClaudeAgentOptions``.
            prompt: Rendered prompt string.

        Returns:
            Accumulated agent text output.

        Raises:
            Exception: If the SDK client fails to create or execute.
        """
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            query,
        )

        options = ClaudeAgentOptions(**sdk_options)
        response_text = ""
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    text = getattr(block, "text", None)
                    if isinstance(text, str):
                        response_text += text
        return response_text

    def _parse_result(
        self,
        task_id: str,
        agent_output: str,
        changes: dict[str, Any],
        execution_time_s: float,
    ) -> TaskResult:
        """Parse observable side effects into a TaskResult.

        Status from OBSERVABLE ARTIFACTS only (Task 5.4 §4):

        - "success": New commits
        - "partial": File changes without commits
        - "failure": No observable changes

        Source: Task 5.4 D5 (git commits as primary success signal).

        Args:
            task_id: Current task identifier.
            agent_output: Accumulated agent text output.
            changes: Change detection results from ``_detect_changes()``.
            execution_time_s: Wall-clock execution time.

        Returns:
            TaskResult with status and metadata.
        """
        new_commits = changes.get("new_commits", [])
        modified_files = changes.get("modified_files", [])
        has_uncommitted = changes.get("has_uncommitted_changes", False)

        if new_commits:
            status = "success"
        elif modified_files or has_uncommitted:
            status = "partial"
        else:
            status = "failure"

        return TaskResult(
            task_id=task_id,
            status=status,
            artifacts=[Path(f) for f in modified_files],
            commits=new_commits,
            metadata={
                "execution_time_s": execution_time_s,
                "agent_output_length": len(agent_output),
                "commit_count": len(new_commits),
                "files_changed": len(modified_files),
                "has_uncommitted_changes": has_uncommitted,
            },
        )
