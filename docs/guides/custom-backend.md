# Writing a Custom AgentBackend

The `AgentBackend` protocol defines how Rigger communicates with a coding agent. The built-in `ClaudeCodeBackend` wraps the Claude Agent SDK, but you can implement `AgentBackend` for any agent.

## The Protocol

```python
from pathlib import Path
from rigger import TaskResult

class AgentBackend:
    async def execute(self, project_root: Path) -> TaskResult: ...
```

That's it — one async method.

## The Contract

### Input: `project_root`

The single argument is the project directory. The agent finds everything it needs on the filesystem:

- `.harness/current_task.json` — The task to work on (written by the Harness before dispatch)
- `.harness/state.json` — Current epoch state
- `.harness/constraints.json` — Dynamic constraints (optional, written by the Harness if constraints produce metadata)
- `AGENTS.md`, `CLAUDE.md` — Project instructions (loaded via `setting_sources`)

### Output: `TaskResult`

Return a `TaskResult` with observable side effects:

```python
from rigger import TaskResult

TaskResult(
    task_id="task-1",
    status="success",       # "success", "failure", "partial", "error"
    artifacts=[Path("src/main.py")],  # Modified files
    commits=["abc123"],     # New git commits
    metadata={"execution_time_s": 45.2},
)
```

### Fresh Context Per Call

Each `execute()` call should create a fresh agent session. The agent has NO memory of previous calls — all continuity comes from the filesystem and git history.

## Reading `.harness/` Files

Use the schema utilities to read `.harness/` files:

```python
from rigger._schema import read_current_task, read_state, read_constraints

task = read_current_task(project_root)    # Task | None
state = read_state(project_root)          # EpochState (always valid)
constraints = read_constraints(project_root)  # dict (empty if absent)
```

## The `setting_sources` Convention

For filesystem-provisioned context (`AGENTS.md`, `CLAUDE.md`) to be loaded by the agent, the backend must configure the SDK appropriately. For `ClaudeCodeBackend`, this means `setting_sources=["project"]`.

When building a backend for a different agent SDK, find the equivalent mechanism to load project-level instructions.

## Example: Skeleton Backend

```python
from pathlib import Path
from rigger import TaskResult
from rigger._schema import read_current_task, read_state

class MyAgentBackend:
    """Backend for a hypothetical coding agent."""

    def __init__(self, model: str = "default") -> None:
        self.model = model

    async def execute(self, project_root: Path) -> TaskResult:
        task = read_current_task(project_root)
        if task is None:
            return TaskResult(task_id="unknown", status="error")

        state = read_state(project_root)

        # Launch your agent here, pointed at project_root
        # The agent reads .harness/current_task.json to know what to do
        result = await self._run_my_agent(project_root, task, state)

        return TaskResult(
            task_id=task.id,
            status="success" if result.ok else "failure",
            commits=result.new_commits,
            artifacts=result.changed_files,
        )

    async def _run_my_agent(self, project_root, task, state):
        # Your agent SDK integration here
        ...
```

## Constraints Merge

If your backend reads `.harness/constraints.json`, it should apply defense-in-depth:

- **`allowed_tools`** — Intersection with constructor allowlist (can only shrink)
- **`disallowed_tools`** — Union with constructor denylist (can only grow)
- **`max_iterations`** — Minimum of file value and constructor limit (can only decrease)

See `ClaudeCodeBackend._build_sdk_options()` for the reference implementation.
