# Workspace Management

Workspace managers provide filesystem isolation for parallel agent execution. Each agent operates in its own copy of the project, and changes are merged back when complete.

## The WorkspaceManager Protocol

```python
from pathlib import Path
from rigger import Task, MergeResult

class WorkspaceManager:
    def create(self, main_root: Path, task: Task, branch_name: str) -> Path: ...
    def merge(self, worktree: Path, main_root: Path) -> MergeResult: ...
    def cleanup(self, worktree: Path) -> None: ...
```

## GitWorktreeManager

Uses `git worktree` to create isolated branches. Best for git-based projects where you want branch-level isolation and merge integration.

```python
from rigger import GitWorktreeManager

wm = GitWorktreeManager()
```

**How it works:**

1. **create()** — Runs `git worktree add` to create a new branch and working directory
2. **merge()** — Runs `git merge --no-ff` to integrate the branch into the main root
3. **cleanup()** — Removes the worktree and deletes the branch

**Requirements:**

- Git 2.17+ (for `git worktree remove`)
- Repository must have at least one commit

**Worktree location:** `<parent>/.rigger-worktrees/<branch_name>`

**Priority coupling:** Tasks are merged sequentially in batch order. Earlier tasks always succeed; later tasks may encounter merge conflicts.

## IndependentDirManager

Copies the entire project directory to a temp location. Works with any project, git or not.

```python
from rigger import IndependentDirManager

wm = IndependentDirManager(prefix="rigger-")
```

**How it works:**

1. **create()** — Runs `shutil.copytree()` to copy the project to a temp directory
2. **merge()** — Runs `shutil.copytree(dirs_exist_ok=True)` to copy changes back
3. **cleanup()** — Removes the temp directory

**When to use:**

- Non-git projects
- CI environments without git
- When branch management overhead is unwanted

## IndependentBranchManager

Creates isolated branches in the same repository without using `git worktree`. Useful when worktrees aren't available or when you want simpler branch-based isolation.

```python
from rigger import IndependentBranchManager

wm = IndependentBranchManager()
```

**How it works:**

1. **create()** — Creates a new branch from HEAD and checks it out in a copied directory
2. **merge()** — Merges the branch back into the original branch
3. **cleanup()** — Removes the temporary directory and deletes the branch

**When to use:**

- Environments where `git worktree` is unavailable
- Simpler branch management without worktree bookkeeping

## Parallel Dispatch Integration

To use parallel dispatch, pass a `WorkspaceManager` to the `Harness` constructor and call `dispatch_parallel()`:

```python
from rigger import Harness, ClaudeCodeBackend, GitWorktreeManager

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(),
    task_source=my_tasks,
    workspace_manager=GitWorktreeManager(),
)

state = harness.load_state()
batch = harness.select_tasks(max_count=3)
provision_result = harness.provision()

results, halt_requested = await harness.dispatch_parallel(
    batch=batch,
    epoch_state=state,
    provision_results=[provision_result],
)
```

**What `dispatch_parallel()` does:**

1. Creates isolated workspaces (one per task)
2. Copies provisioned content into each workspace
3. Writes `.harness/` files (task + state) per workspace
4. Dispatches all agents concurrently via `asyncio.gather(return_exceptions=True)`
5. Verifies results per workspace
6. Merges changes back sequentially
7. Runs post-merge constraint checks
8. Cleans up all workspaces

A failure in one agent does not cancel others — each agent runs independently.
