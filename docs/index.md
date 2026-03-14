# Rigger

A declarative Python framework for building external harnesses around opaque coding agents.

Rigger lets you compose protocol-based plugins across 6 orthogonal dimensions — task decomposition, context provisioning, verification, constraints, state continuity, and entropy management — to build structured harnesses that wrap any coding agent. The agent is a black box; Rigger manages everything external to it.

## Features

- **Declarative YAML config** — Define your harness in `harness.yaml`, run with `rigger`. No Python required.
- **22 built-in components** — Ready-to-use implementations across all 6 dimensions
- **6 dimension protocols** — Each aspect of harness behavior is a separate `typing.Protocol` that you implement and plug in
- **CLI** — `rigger run`, `rigger init`, `rigger status` for zero-code workflows
- **Templates** — Start from pre-built templates (`gsd`, `openai`) or create your own
- **Plugin discovery** — Third-party components auto-discovered via `importlib.metadata` entry points
- **Canonical epoch loop** — `Harness.run()` orchestrates the full lifecycle, or use step methods for custom loops
- **Async-native** — Built on `asyncio` for concurrent dispatch and long-running agent calls
- **Parallel dispatch** — Run multiple agents in isolated workspaces with `GitWorktreeManager`, `IndependentDirManager`, or `IndependentBranchManager`
- **`.harness/` bilateral protocol** — Versioned filesystem contract between harness and backend with atomic read/write

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

## Next Steps

- [Getting Started](getting-started.md) — Installation and your first harness
- [CLI Reference](cli.md) — All commands and options
- [Built-in Components](built-in-components.md) — All 22 ready-to-use implementations
- [Concepts](concepts.md) — Architecture, protocols, and design decisions
- [API Reference](api/index.md) — Full API documentation
