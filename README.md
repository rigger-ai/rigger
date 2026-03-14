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
rigger init
```

This generates a `harness.yaml` — edit it to configure your harness:

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

Then run:

```bash
rigger
```

### Templates

Start from a pre-built template instead:

```bash
rigger init --template gsd        # minimal get-shit-done config
rigger init --template openai     # multi-agent OpenAI-style harness
rigger init --list-templates      # see all available templates
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

## Built-in Components

22 implementations ship with the framework, all usable from YAML:

| Dimension | Type Name | Class |
|-----------|-----------|-------|
| Task Source | `file_list` | `FileListTaskSource` |
| Task Source | `json_stories` | `JsonStoriesTaskSource` |
| Task Source | `linear` | `LinearTaskSource` |
| Task Source | `atomic_issue` | `AtomicIssueTaskSource` |
| Context Source | `file_tree` | `FileTreeContextSource` |
| Context Source | `agents_md` | `AgentsMdContextSource` |
| Context Source | `static_files` | `StaticFilesContextSource` |
| Context Source | `mcp_capability` | `McpCapabilityContextSource` |
| Verifier | `test_suite` | `TestSuiteVerifier` |
| Verifier | `lint` | `LintVerifier` |
| Verifier | `ci_status` | `CiStatusVerifier` |
| Verifier | `ratchet` | `RatchetVerifier` |
| Constraint | `tool_allowlist` | `ToolAllowlistConstraint` |
| Constraint | `branch_policy` | `BranchPolicyConstraint` |
| State Store | `json_file` | `JsonFileStateStore` |
| State Store | `harness_dir` | `HarnessDirStateStore` |
| Entropy Detector | `shell_command` | `ShellCommandEntropyDetector` |
| Entropy Detector | `doc_staleness` | `DocStalenessEntropyDetector` |
| Workspace | `git_worktree` | `GitWorktreeManager` |
| Workspace | `independent_dir` | `IndependentDirManager` |
| Workspace | `independent_branch` | `IndependentBranchManager` |
| Backend | `claude_code` | `ClaudeCodeBackend` |

Third-party plugins are discovered via `importlib.metadata` entry points under `rigger.<protocol>`.

## Architecture

The core loop follows a deterministic phase sequence:

```
READ_STATE → SELECT_TASK → PROVISION → CHECK_PRE → DISPATCH → VERIFY → PERSIST
```

The `Harness` class orchestrates this loop. The agent (`AgentBackend`) is a black box that receives a `project_root` and navigates the filesystem using its own tools. Task assignments and context are communicated through the `.harness/` bilateral filesystem protocol.

## Four Tiers of Flexibility

1. **YAML + CLI** — Zero Python. Define everything in `harness.yaml`, run with `rigger`. Covers all 22 built-in implementations.

2. **`run()` / `run_sync()`** — The blessed canonical loop. Handles state, task selection, provisioning, dispatch, verification, and persistence automatically.

3. **Step methods** — `load_state()`, `select_tasks()`, `provision()`, `dispatch()`, `verify()`, `persist()`. Build your own loop from composable steps (tf.GradientTape equivalent).

4. **Direct protocol usage** — Instantiate and call protocol implementations directly for maximum control.

## CLI

```bash
rigger                          # run (default command)
rigger run --config my.yaml     # explicit config path
rigger run --dry-run            # validate config without executing
rigger run --force              # override existing lock file
rigger status                   # show current .harness/ state
rigger init                     # generate starter harness.yaml
rigger init --template gsd      # init from a built-in template
rigger init --list-templates    # list available templates
```

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
