# Rigger

A declarative Python framework for building external harnesses around opaque coding agents.

Rigger lets you compose protocol-based plugins across 6 orthogonal dimensions — task decomposition, context provisioning, verification, constraints, state continuity, and entropy management — to build structured harnesses that wrap any coding agent. The agent is a black box; Rigger manages everything external to it.

## Features

- **6 dimension protocols** — Each aspect of harness behavior is a separate `typing.Protocol` that you implement and plug in
- **Protocol-based extensibility** — Duck-typed interfaces with no class hierarchy to inherit from
- **Canonical epoch loop** — `Harness.run()` orchestrates the full lifecycle, or use step methods for custom loops
- **Async-native** — Built on `asyncio` for concurrent dispatch and long-running agent calls
- **Parallel dispatch** — Run multiple agents in isolated workspaces with `GitWorktreeManager` or `IndependentDirManager`
- **`.harness/` bilateral protocol** — Versioned filesystem contract between harness and backend with atomic read/write

## Quick Install

```bash
pip install rigger
```

## Minimal Example

```python
from pathlib import Path
from rigger import Harness, Task, TaskResult, ClaudeCodeBackend

class MyTasks:
    def __init__(self, tasks: list[Task]):
        self._tasks = list(tasks)

    def pending(self, project_root: Path) -> list[Task]:
        return self._tasks

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(model="claude-sonnet-4-6"),
    task_source=MyTasks([Task(id="1", description="Add input validation")]),
)
state = harness.run_sync(max_epochs=1)
```

## Next Steps

- [Getting Started](getting-started.md) — Installation and your first harness
- [Concepts](concepts.md) — Architecture, protocols, and design decisions
- [API Reference](api/index.md) — Full API documentation
