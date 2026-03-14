# CLI Reference

Rigger ships a `rigger` command with three subcommands. When invoked without a subcommand, it defaults to `run`.

## `rigger run`

Run the harness loop.

```bash
rigger                          # default — same as rigger run
rigger run                      # explicit
rigger run --config my.yaml     # custom config path (default: harness.yaml)
rigger run --dry-run            # parse and validate config without executing
rigger run --force              # override existing lock file
rigger run -v                   # verbose logging (DEBUG level)
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | All tasks completed successfully |
| 1 | Harness halted (BLOCK, ESCALATE, or max retries exhausted) |
| 2 | Max epochs reached without completion |
| 3 | Configuration error (invalid YAML, unknown types, missing params) |
| 4 | Lock conflict (another harness instance is running) |

### Lock file

When a harness starts, it writes `harness.lock` in the project root. This prevents two instances from running concurrently. Use `--force` to override a stale lock.

## `rigger status`

Display current harness state from the `.harness/` directory.

```bash
rigger status
```

Shows epoch count, completed/pending tasks, progress percentage, halted status, and lock info.

## `rigger init`

Generate a starter `harness.yaml` or copy a built-in template.

```bash
rigger init                         # generate starter harness.yaml
rigger init -o custom.yaml          # custom output path
rigger init --template gsd          # copy the gsd template
rigger init --template openai       # copy the openai template
rigger init --list-templates        # list available templates
```

### Built-in templates

| Template | Description |
|----------|-------------|
| `gsd` | Minimal get-shit-done config — test suite as sole gate, no extras |
| `openai` | Multi-agent OpenAI-style harness with AGENTS.md, conventions, and design docs |

Templates copy all relevant files (YAML, task definitions, docs) into the current directory.

## Global options

These options are available on all subcommands:

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to harness.yaml (default: `harness.yaml`) |
| `--force` | Override existing lock file |
| `-v`, `--verbose` | Increase log verbosity to DEBUG |
| `--dry-run` | Parse and validate config without running |
| `--version` | Show version and exit |
