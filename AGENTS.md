# Agent Instructions for rigger

## Overview

Rigger is a Keras-like Python framework for building external harnesses around opaque coding agents (Claude Agents SDK backend). The agent is a **black box** — Rigger models only external, observable patterns.

## Architecture Summary

### 6 Dimensions

Rigger decomposes harness behavior into 6 orthogonal dimensions, each backed by a `typing.Protocol`:

| Dimension | Code | Protocol | Key Method |
|-----------|------|----------|------------|
| Context Provisioning | CP | `ContextSource` | `gather(project_root) -> ProvisionResult` |
| Feedback Loop | FL | `Verifier` | `verify(project_root, result) -> VerifyResult` |
| Task Decomposition | TD | `TaskSource` | `pending(project_root) -> list[Task]` |
| Agent Constraints | AC | `Constraint` | `check(project_root) -> VerifyResult` |
| State Continuity | SC | `StateStore` | `load(project_root) -> EpochState`, `save(project_root, state) -> None` |
| Entropy Management | EM | `EntropyDetector` | `scan(project_root) -> list[Task]` |

The orchestration loop is `Harness.run()` — it is NOT a 7th dimension.

### Core Loop

```
READ_STATE → SELECT_TASK → PROVISION → CHECK_PRE → DISPATCH → EXECUTE → VERIFY → HARVEST → PERSIST
```

### `.harness/` Bilateral Protocol

The `.harness/` directory is the coupling point between the Harness and the Backend:
- Harness writes: `current_task.json` (MUST), `state.json` (MUST), `constraints.json` (MAY)
- Backend reads these files to understand what to do
- Write order: state → task → (constraints) → execute

## 12 Key Design Decisions

Every implementor MUST follow these validated decisions:

1. **Composition over inheritance** (Finding 7.1) — Protocols are duck-typed, no class hierarchy
2. **Filesystem effects, not string injection** (Finding 7.2) — ContextSources write files, agents discover them
3. **Single ContextProvisioner class** (Finding 7.13) — No hierarchy; aggregation with dedup and conflict detection
4. **Harness.run() is the loop** (Finding 7.8) — 6 dimensions are plugins, loop is NOT a dimension
5. **AgentBackend.execute(project_root)** (Finding 7.17) — Single arg, no task/context injection
6. **Step methods for custom loops** (Finding 7.18) — tf.GradientTape equivalent
7. **Async execute via asyncio** (Finding 7.21) — `async def execute()`, `async def run()`
8. **setting_sources=["project"] MUST** (Finding 7.56) — Required for ClaudeCodeBackend
9. **No ContextSource setup()/teardown()** (Finding 7.51) — Use context managers + WorkspaceManager decorators
10. **Partitioned .harness/ files for concurrency** (Finding 7.55) — `tasks_{ts}_{uuid}.json`, no shared mutable file
11. **asyncio.gather(return_exceptions=True)** (Finding 7.54) — Parallel dispatch model, WM stays sync via `to_thread()`
12. **ContextSource MUST NOT write to .harness/** (Finding 7.58) — Discoverable vs guaranteed-in-prompt boundary

## Package Structure

```
src/rigger/
  __init__.py              # Public API re-exports
  _types.py                # Task, TaskResult, EpochState, ProvisionResult, VerifyResult
  _protocols.py            # TaskSource, ContextSource, Verifier, Constraint, StateStore, EntropyDetector, AgentBackend
  _provisioner.py          # ContextProvisioner, CriticalSource
  _harness.py              # Harness class (run, run_once, run_sync, step methods, parallel dispatch)
  _merge.py                # Metadata merge algorithm (additive, restrictive, scalar-min)
  _schema.py               # .harness/ read/write utilities with atomic writes
  py.typed                 # PEP 561 marker
  backends/
    __init__.py
    claude_code.py          # ClaudeCodeBackend (Claude Code SDK wrapper)
  workspace/
    __init__.py
    git_worktree.py         # GitWorktreeManager
    independent.py          # IndependentDirManager
```

Underscore-prefixed modules are internal. Public API is re-exported via `__init__.py`.

## Code Style

- Python 3.13+ with type hints on all functions
- `typing.Protocol` for all extension points
- `@dataclass` for data containers
- Google-style docstrings (enforced by ruff `D` rules)
- Async where specified (`execute`, `run`, `dispatch`)
- Minimal dependencies for MVP (stdlib + `claude-agent-sdk`)

## Testing

- All tests in `tests/` directory
- pytest with fixtures, pytest-asyncio for async tests
- Unit tests per module
- Integration tests using golden harnesses as behavioral specifications
- 80% coverage target per feature

### Quality Checks

```bash
uv run ruff check --fix . && uv run ruff format . && uvx ty check && uv run pytest
```
