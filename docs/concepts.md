# Concepts

## The 6 Dimensions

Rigger decomposes harness behavior into 6 orthogonal dimensions. Each dimension is a `typing.Protocol` — implement the methods and plug it into the `Harness` constructor.

| Dimension | Code | Protocol | Key Method | Purpose |
|-----------|------|----------|------------|---------|
| Task Decomposition | TD | `TaskSource` | `pending()`, `mark_complete()` | Provides the next task(s) to execute |
| Context Provisioning | CP | `ContextSource` | `gather()` | Prepares filesystem artifacts for the agent to discover |
| Feedback Loop | FL | `Verifier` | `verify()` | Checks agent output against quality criteria |
| Agent Constraints | AC | `Constraint` | `check()` | Enforces architectural invariants pre/post dispatch |
| State Continuity | SC | `StateStore` | `load()`, `save()` | Persists and restores state across epochs |
| Entropy Management | EM | `EntropyDetector` | `scan()` | Detects drift, degradation, and generates remediation tasks |

The orchestration loop (`Harness.run()`) is NOT a dimension — it's the framework that composes them.

## Core Loop

The `Harness` executes a canonical epoch loop with deterministic phase ordering:

```
READ_STATE → SELECT_TASK → PROVISION → CHECK_PRE → DISPATCH → VERIFY → PERSIST
```

Each phase maps to a step method:

| Phase | Step Method | What Happens |
|-------|-------------|-------------|
| READ_STATE | `load_state()` | Load `EpochState` from `StateStore` or `.harness/state.json` |
| SELECT_TASK | `select_tasks()` | Get next task(s) from `TaskSource.pending()` |
| PROVISION | `provision()` | Aggregate `ContextSource.gather()` results |
| CHECK_PRE | `check_constraints()` | Run `Constraint.check()` before dispatch |
| DISPATCH | `dispatch()` | Write `.harness/current_task.json`, call `AgentBackend.execute()` |
| VERIFY | `verify()` | Run `Verifier.verify()` on the `TaskResult` |
| PERSIST | `persist()` | Write `.harness/state.json`, call `StateStore.save()` |

After persistence, `EntropyDetector.scan()` runs to detect drift, and the loop checks the stop predicate.

## The `.harness/` Bilateral Protocol

The `.harness/` directory is the coupling point between the Harness (loop controller) and the Backend (agent wrapper):

**Harness writes:**

- `current_task.json` (MUST) — The task the agent should work on
- `state.json` (MUST) — Current epoch state
- `constraints.json` (MAY) — Dynamic constraints from `Constraint.check()` metadata

**Backend reads** these files to understand what to do. The agent navigates the rest of the project using its own tools.

All writes are atomic (temp file + `os.replace()`). All reads are resilient to missing files and malformed JSON. Schema versions use additive-only evolution with major-version compatibility checks.

## Three Tiers of Flexibility

### Tier 1: `run()` — The Blessed Loop

For most use cases, call `run()` (async) or `run_sync()` and let the framework handle everything:

```python
state = harness.run_sync(max_epochs=10, stop_when=all_tasks_done)
```

Use `Callbacks` for lifecycle hooks without writing a custom loop:

```python
from rigger import Callbacks, Action

callbacks = Callbacks(
    on_task_complete=lambda result: Action.HALT if result.status == "error" else None,
)
state = await harness.run(max_epochs=10, callbacks=callbacks)
```

### Tier 2: Step Methods — Custom Loops

For advanced control, compose step methods into your own loop:

```python
state = harness.load_state()
tasks = harness.select_tasks()
provision_result = harness.provision()
pre_results = harness.check_constraints()
result = await harness.dispatch(tasks[0])
verify_results = harness.verify(result)
harness.persist(state)
```

### Tier 3: Direct Protocol Usage

Instantiate protocol implementations directly for maximum control over individual dimensions.

## ContextProvisioner and CriticalSource

`ContextProvisioner` aggregates multiple `ContextSource` instances:

- Files are deduplicated by resolved path (first-seen wins)
- Capabilities are concatenated in source order
- Failing sources are logged and **skipped** (fail-open default)

Wrap a source in `CriticalSource` to make its failure abort provisioning:

```python
from rigger import ContextProvisioner, CriticalSource

provisioner = ContextProvisioner(sources=[
    CriticalSource(essential_source),  # Failure aborts provisioning
    optional_source,                    # Failure is logged and skipped
])
```

### Delivery Boundary

`ContextSource.gather()` provisions **discoverable** content — filesystem artifacts the agent MAY find during execution. It does NOT guarantee prompt inclusion.

Guaranteed-in-prompt delivery is owned by:

- **`AgentBackend`** — for always-loaded files (e.g., `CLAUDE.md`, `AGENTS.md`) via `setting_sources`
- **`TaskSource`** — for task descriptions that embed domain context

## Parallel Dispatch and WorkspaceManager

For concurrent task execution, provide a `WorkspaceManager` and use `dispatch_parallel()`:

```python
from rigger import GitWorktreeManager

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(),
    task_source=my_tasks,
    workspace_manager=GitWorktreeManager(),
)

# Dispatch multiple tasks concurrently
results, halt = await harness.dispatch_parallel(
    batch=tasks,
    epoch_state=state,
)
```

Each task runs in an isolated workspace. Results are merged back sequentially (priority-coupled — earlier tasks in the batch merge first).

Two implementations are provided:

- **`GitWorktreeManager`** — Uses `git worktree` for branch-based isolation with merge back
- **`IndependentDirManager`** — Copies the project directory (no git required)

## Key Design Decisions

1. **Composition over inheritance** — Protocols are duck-typed, no class hierarchy
2. **Filesystem effects, not string injection** — ContextSources write files, agents discover them
3. **AgentBackend.execute(project_root)** — Single arg, agent navigates the filesystem
4. **Async-native** — `execute()`, `run()`, `dispatch()` are all async
5. **`.harness/` is Rigger-owned** — ContextSources MUST NOT write to `.harness/`
6. **setting_sources=["project"]** — Required convention for `ClaudeCodeBackend`
