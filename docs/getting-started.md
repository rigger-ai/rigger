# Getting Started

## Installation

### From PyPI

```bash
pip install rigger
```

### From source

```bash
git clone https://github.com/rigger-ai/rigger.git
cd rigger
uv sync
```

## Your First Harness

A Rigger harness needs at minimum a **backend** (the coding agent) and a **task source** (what to work on).

### 1. Define a TaskSource

`TaskSource` is a protocol with two methods: `pending()` returns tasks in priority order, and `mark_complete()` updates task status.

```python
from pathlib import Path
from rigger import Task, TaskResult

class FileTaskSource:
    """Reads tasks from a JSON file."""

    def __init__(self, tasks: list[Task]):
        self._tasks = list(tasks)

    def pending(self, project_root: Path) -> list[Task]:
        return self._tasks

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]
```

### 2. Create and run the Harness

```python
from rigger import Harness, ClaudeCodeBackend

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(model="claude-sonnet-4-6"),
    task_source=FileTaskSource([
        Task(id="1", description="Set up the project structure"),
        Task(id="2", description="Implement the data model"),
    ]),
)

# Run through all tasks (one per epoch)
state = harness.run_sync(max_epochs=10)
print(f"Completed: {state.completed_tasks}")
```

## Adding Verification

Use `Verifier` to check agent output after each task:

```python
from rigger import VerifyResult, TaskResult

class TestVerifier:
    """Runs the test suite and checks for failures."""

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        import subprocess
        proc = subprocess.run(
            ["uv", "run", "pytest"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        return VerifyResult(
            passed=proc.returncode == 0,
            message="Tests passed" if proc.returncode == 0 else proc.stdout,
        )

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(),
    task_source=my_tasks,
    verifiers=[TestVerifier()],
)
```

## Adding Constraints

Use `Constraint` to enforce invariants before and after agent execution:

```python
from rigger import VerifyResult

class NoSecretFiles:
    """Ensures no .env files are committed."""

    def check(self, project_root: Path) -> VerifyResult:
        env_files = list(project_root.rglob(".env*"))
        return VerifyResult(
            passed=len(env_files) == 0,
            message=f"Found {len(env_files)} .env files" if env_files else "",
        )

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(),
    task_source=my_tasks,
    constraints=[NoSecretFiles()],
)
```

## Adding Context

Use `ContextSource` to prepare filesystem artifacts the agent can discover:

```python
from rigger import ProvisionResult

class ProjectDocsSource:
    """Ensures API documentation is available in the project."""

    def gather(self, project_root: Path) -> ProvisionResult:
        docs_dir = project_root / "docs"
        files = list(docs_dir.rglob("*.md")) if docs_dir.exists() else []
        return ProvisionResult(files=files, capabilities=["project-docs"])

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(),
    task_source=my_tasks,
    context_sources=[ProjectDocsSource()],
)
```

## Development Setup

### Prerequisites

- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Install dependencies

```bash
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

### Preview docs

```bash
uv run --group docs mkdocs serve
```
