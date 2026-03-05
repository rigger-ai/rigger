# Rigger

[![CI](https://github.com/rigger-ai/rigger/actions/workflows/ci.yml/badge.svg)](https://github.com/rigger-ai/rigger/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/rigger)](https://pypi.org/project/rigger/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-rigger--ai.github.io-blue)](https://rigger-ai.github.io/rigger/)

A declarative Python framework for building external harnesses around opaque coding agents.

## Why Rigger

Coding agents are powerful but unpredictable. Rigger gives you a structured way to wrap any coding agent in an external harness that manages tasks, provides context, verifies output, and enforces constraints — without modeling the agent's internals. Think Keras for agent orchestration: compose protocol-based plugins across 6 orthogonal dimensions, and let the framework handle the loop.

## Quick Start

```bash
pip install rigger
```

```python
from pathlib import Path
from rigger import Harness, Task, TaskResult, ClaudeCodeBackend

# Implement a minimal TaskSource
class MyTasks:
    def __init__(self, tasks: list[Task]):
        self._tasks = list(tasks)

    def pending(self, project_root: Path) -> list[Task]:
        return self._tasks

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

# Wire up and run
harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(model="claude-sonnet-4-6"),
    task_source=MyTasks([Task(id="1", description="Add input validation")]),
)
state = harness.run_sync(max_epochs=1)
```

## Key Concepts

Rigger decomposes harness behavior into 6 orthogonal dimensions:

| Dimension | Protocol | Purpose |
|-----------|----------|---------|
| Task Decomposition | `TaskSource` | Provides the next task(s) to execute |
| Context Provisioning | `ContextSource` | Prepares filesystem artifacts for the agent |
| Feedback Loop | `Verifier` | Checks agent output against quality criteria |
| Agent Constraints | `Constraint` | Enforces architectural invariants pre/post dispatch |
| State Continuity | `StateStore` | Persists and restores state across epochs |
| Entropy Management | `EntropyDetector` | Detects drift and generates remediation tasks |

Each dimension is a `typing.Protocol` — implement the methods, plug it in.

## Architecture

The core loop follows a deterministic phase sequence:

```
READ_STATE → SELECT_TASK → PROVISION → CHECK_PRE → DISPATCH → VERIFY → PERSIST
```

The `Harness` class orchestrates this loop. The agent (`AgentBackend`) is a black box that receives a `project_root` and navigates the filesystem using its own tools. Task assignments and context are communicated through the `.harness/` bilateral filesystem protocol.

## Three Tiers of Flexibility

1. **`run()` / `run_sync()`** — The blessed canonical loop. Handles state, task selection, provisioning, dispatch, verification, and persistence automatically.

2. **Step methods** — `load_state()`, `select_tasks()`, `provision()`, `dispatch()`, `verify()`, `persist()`. Build your own loop from composable steps (tf.GradientTape equivalent).

3. **Direct protocol usage** — Instantiate and call protocol implementations directly for maximum control.

## Development

### Prerequisites

- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
git clone https://github.com/rigger-ai/rigger.git
cd rigger
uv sync
```

### Run tests

```bash
uv run pytest
```

### Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uvx ty check
```

### Documentation

```bash
uv run --group docs mkdocs serve
```

## Documentation

Full documentation is available at [rigger-ai.github.io/rigger](https://rigger-ai.github.io/rigger/).

## License

Apache-2.0
