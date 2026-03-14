# SWE-bench Verified Benchmark

Run Rigger as a Harbor agent on SWE-bench Verified instances. This is a **benchmark test**: expensive, slow, requires Docker + API keys. Run manually on major changes, not in CI.

## Prerequisites

```bash
# Install with harbor extras
uv sync --group harbor

# Ensure Docker is running
docker info
```

## Run (recommended — agent self-verifies)

```bash
harbor run -d swebench-verified@1.0 \
  --agent-import-path rigger.harbor.agent:RiggerAgent \
  -m anthropic/claude-sonnet-4-6 \
  --ak max_turns=50 \
  --n-tasks 1
```

The agent receives a rich SWE-bench prompt with a structured workflow (explore, reproduce, fix, verify via `pytest`, review via `git diff`). No `test_command` needed — the agent finds and runs the relevant tests itself.

## Run (with external verification + retry loop)

```bash
harbor run -d swebench-verified@1.0 \
  --agent-import-path rigger.harbor.agent:RiggerAgent \
  -m anthropic/claude-sonnet-4-6 \
  --ak max_turns=30 \
  --ak max_retries=2 \
  --ak 'test_command=cd /testbed && python -m pytest <test_file> -x --tb=short 2>&1 | tail -100' \
  --n-tasks 1
```

With `test_command`, Rigger uses `Harness.run()` with the full dispatch+verify retry loop. On test failure, the agent receives feedback with truncated test output and retries up to `max_retries` times.

## What Rigger does

| Component | Work |
|-----------|------|
| `Harness.run()` | Full pipeline: provision, constraints, dispatch, verify, retry loop |
| `ContainerTestVerifier` | Runs test command in container, writes feedback.json on failure |
| `InstructionTaskSource` | Converts Harbor instruction string to Rigger Task |
| `HarborBackend.execute()` | Uploads .harness/, runs Claude CLI with rich prompt, reads feedback.json for retries |
| `HarnessDirStateStore` | Persists EpochState to .harness/state.json |

## Agent kwargs

| Key | Default | Description |
|-----|---------|-------------|
| `max_turns` | 30 | Maximum Claude CLI conversation turns. Higher = more exploration time. |
| `test_command` | None | Shell command to run in container for verification. Enables retry loop. |
| `max_retries` | 2 | Maximum retry attempts when tests fail. |
