# Contributing to rigger

Thank you for your interest in contributing to rigger!

## Development Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/rigger-ai/rigger.git
   cd rigger
   ```

2. Install dependencies with [uv](https://docs.astral.sh/uv/):
   ```bash
   uv sync
   ```

3. Run the test suite to verify your setup:
   ```bash
   uv run pytest
   ```

## Code Style

- **Linting & formatting**: [Ruff](https://docs.astral.sh/ruff/)
- **Type checking**: [ty](https://docs.astral.sh/ty/)
- **Docstrings**: Google style (enforced by ruff)
- **Type hints**: Required on all public functions

## Quality Checks

Run all checks before submitting a PR:

```bash
uv run ruff check .
uv run ruff format --check .
uvx ty check
uv run pytest
```

## Pull Requests

1. Create a feature branch from `main`.
2. Make your changes with clear, focused commits.
3. Ensure all quality checks pass.
4. Open a pull request with a clear description.

## Reporting Issues

Use [GitHub Issues](https://github.com/rigger-ai/rigger/issues) to report bugs or request features.
