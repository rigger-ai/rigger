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

### Option 1: Declarative (YAML + CLI)

The fastest way to get started — no Python required.

```bash
rigger init
```

This creates a `harness.yaml`. Edit it:

```yaml
backend:
  type: claude_code

task_source:
  type: file_list
  path: tasks.txt

verifiers:
  - type: test_suite
    command: ["python", "-m", "pytest", "--tb=short", "-q"]

run:
  max_epochs: 20
  max_retries: 2
  stop_when: all_tasks_done
```

Create a `tasks.txt` with one task per line, then run:

```bash
rigger
```

Or start from a template:

```bash
rigger init --template gsd
```

See [CLI Reference](cli.md) for all options and [Built-in Components](built-in-components.md) for all available types.

### Option 2: Python API

For programmatic control, use `Harness` directly:

```python
from pathlib import Path
from rigger import Harness, ClaudeCodeBackend, FileListTaskSource, TestSuiteVerifier

harness = Harness(
    project_root=Path("my-project"),
    backend=ClaudeCodeBackend(model="claude-sonnet-4-6"),
    task_source=FileListTaskSource(path=Path("tasks.json")),
    verifiers=[TestSuiteVerifier(command=["pytest"])],
)

state = harness.run_sync(max_epochs=10)
print(f"Completed: {len(state.completed_tasks)} tasks in {state.epoch} epochs")
```

### Option 3: Custom Protocols

Implement the protocols yourself for maximum flexibility:

```python
from pathlib import Path
from rigger import Task, TaskResult

class MyTaskSource:
    def __init__(self, tasks: list[Task]):
        self._tasks = list(tasks)

    def pending(self, project_root: Path) -> list[Task]:
        return self._tasks

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]
```

Each dimension is a `typing.Protocol` — implement the methods, plug it in. See [Concepts](concepts.md) for the full protocol reference.

## Adding Verification

### YAML

```yaml
verifiers:
  - type: test_suite
    command: ["python", "-m", "pytest"]
  - type: lint
    command: ruff check .
  - type: ratchet
    metric: coverage
    threshold: 80.0
```

### Python

```python
from rigger import VerifyResult, TaskResult

class MyVerifier:
    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        import subprocess
        proc = subprocess.run(
            ["pytest"], cwd=project_root, capture_output=True, text=True,
        )
        return VerifyResult(
            passed=proc.returncode == 0,
            message="Tests passed" if proc.returncode == 0 else proc.stdout,
        )
```

## Adding Constraints

### YAML

```yaml
constraints:
  - type: tool_allowlist
    tools: [Read, Edit, Bash]
  - type: branch_policy
    pattern: "feature/*"
```

### Python

```python
from rigger import VerifyResult

class NoSecretFiles:
    def check(self, project_root: Path) -> VerifyResult:
        env_files = list(project_root.rglob(".env*"))
        return VerifyResult(
            passed=len(env_files) == 0,
            message=f"Found {len(env_files)} .env files" if env_files else "",
        )
```

## Adding Context

### YAML

```yaml
context_sources:
  - type: file_tree
    root: src/
  - type: agents_md
  - type: static_files
    paths:
      - docs/architecture.md
```

### Python

```python
from rigger import ProvisionResult

class ProjectDocsSource:
    def gather(self, project_root: Path) -> ProvisionResult:
        docs_dir = project_root / "docs"
        files = list(docs_dir.rglob("*.md")) if docs_dir.exists() else []
        return ProvisionResult(files=files, capabilities=["project-docs"])
```

## Environment Variable Interpolation

YAML config supports `${VAR}` syntax for environment variables:

```yaml
task_source:
  type: linear
  team_id: ${LINEAR_TEAM_ID}
  api_key: ${LINEAR_API_KEY}
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
