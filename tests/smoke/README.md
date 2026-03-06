# Rigger Smoke Test

Manual live test against a real Claude agent.

## Prerequisites

- Authentication: either `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` environment variable set
- `rigger` package installed (`uv pip install -e .` from repo root)

## Steps

1. Initialize a temporary git repo:
   ```bash
   cd tests/smoke
   git init
   git add .
   git commit -m "init"
   ```

2. Run the harness:
   ```bash
   rigger run
   ```

   **Note:** If running from inside a Claude Code session, the SDK's nesting
   guard will block execution. Unset the env var first:
   ```bash
   CLAUDECODE= rigger run
   ```

3. Expected outcome:
   - Task "hello" completes in 1 epoch
   - `hello.txt` is created with "Hello, World!"
   - Exit code 0
   - Output: "Completed -- 1 tasks done in 1 epochs."

## Cleanup

```bash
rm -rf .git .harness hello.txt
```
