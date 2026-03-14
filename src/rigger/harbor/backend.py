"""HarborBackend — AgentBackend that runs Claude CLI inside a Harbor container."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from rigger._schema import read_current_task
from rigger._types import TaskResult

logger = logging.getLogger(__name__)

_FIRST_ATTEMPT_PROMPT = """\
You are an expert software engineer fixing a bug in a repository at /testbed/.

## Task
{description}

## Workflow
1. **Understand the problem**: Read the issue description thoroughly.
2. **Explore**: Use find, grep, and cat to locate relevant source files.
3. **Reproduce**: Write a small script or commands to confirm the bug.
4. **Fix**: Make the minimal change needed. Do NOT modify test files.
5. **Verify**: Re-run your reproduction, then find and run the relevant test suite:
   ```
   find . -path '*/tests/*' -name '*.py' | grep -i <module>
   python -m pytest <test_file> -x --tb=short
   ```
6. **Review**: Run `git diff` to check your changes are minimal and correct.

Do NOT modify test files. Do NOT run git commit.\
"""

_RETRY_PROMPT = """\
Your previous attempt FAILED verification.

Test command: {test_command}
Output:
```
{test_output}
```

Your previous changes are still in the working tree. Run `git diff` to see them.

1. Analyze the test failures above.
2. Identify why your fix is wrong or incomplete.
3. Fix the issues — you may need a different approach.
4. Run the tests again to verify.
5. Run `git diff` to review your final changes.

## Original Task
{description}

Do NOT modify test files. Do NOT run git commit.\
"""

# OAuth constants from Claude Code binary (prod config)
_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_KEYCHAIN_SERVICE = "Claude Code-credentials"


def _read_keychain_credentials() -> tuple[dict, str] | None:
    """Read Claude Code credentials JSON from macOS keychain.

    Tries the default and profile-specific keychain entries, returning
    whichever has the freshest (or only valid) OAuth token.

    Returns:
        Tuple of (credentials dict, service name) or None.
    """
    best: tuple[dict, str, int] | None = None

    # Find all credential entries
    try:
        dump = subprocess.run(
            ["security", "dump-keychain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        services = set()
        for line in dump.stdout.splitlines():
            if _KEYCHAIN_SERVICE in line:
                # Extract service name from: "svce"<blob>="Claude Code-credentials-xxx"
                start = line.find(f'"{_KEYCHAIN_SERVICE}')
                if start >= 0:
                    end = line.find('"', start + 1)
                    if end >= 0:
                        services.add(line[start + 1 : end])
        if not services:
            services = {_KEYCHAIN_SERVICE}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        services = {_KEYCHAIN_SERVICE}

    for svc in sorted(services):
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", svc, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                continue
            data = json.loads(result.stdout.strip())
            oauth = data.get("claudeAiOauth", {})
            expires = oauth.get("expiresAt", 0)
            if best is None or expires > best[2]:
                best = (data, svc, expires)
        except (json.JSONDecodeError, subprocess.TimeoutExpired):
            continue

    if best is None:
        return None
    return best[0], best[1]


def _write_keychain_credentials(creds: dict, service: str) -> None:
    """Update Claude Code credentials in macOS keychain."""
    payload = json.dumps(creds)
    account = os.environ.get("USER", "")
    # Delete then re-add (security doesn't have an update command)
    subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        capture_output=True,
        timeout=5,
        check=False,
    )
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            payload,
        ],
        capture_output=True,
        timeout=5,
        check=False,
    )


def _refresh_oauth_token(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a fresh access token."""
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _CLIENT_ID,
        }
    ).encode()
    req = urllib.request.Request(
        _TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "claude-code/2.1.70",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception:
        logger.warning("Failed to refresh OAuth token", exc_info=True)
        return None


def _get_oauth_token() -> str:
    """Retrieve a valid Claude Code OAuth token.

    Resolution order:
    1. ``CLAUDE_CODE_OAUTH_TOKEN`` env var (if set)
    2. macOS keychain ``Claude Code-credentials`` — refreshes if expired
    3. Empty string (fall through to ANTHROPIC_API_KEY)
    """
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if token:
        return token

    result = _read_keychain_credentials()
    if result is None:
        return ""

    creds, service = result
    oauth = creds.get("claudeAiOauth", {})
    access_token = oauth.get("accessToken", "")
    expires_at = oauth.get("expiresAt", 0)
    refresh_token = oauth.get("refreshToken", "")

    # Check if token is still valid (with 60s buffer)
    now_ms = int(time.time() * 1000)
    if access_token and expires_at > now_ms + 60_000:
        return access_token

    # Token expired — refresh it
    if not refresh_token:
        logger.warning("OAuth token expired and no refresh token available")
        return access_token  # return stale token as best effort

    logger.info("OAuth token expired, refreshing via %s...", service)
    resp = _refresh_oauth_token(refresh_token)
    if resp and "access_token" in resp:
        new_token = resp["access_token"]
        expires_in = resp.get("expires_in", 28800)
        new_refresh = resp.get("refresh_token", refresh_token)

        # Update keychain
        oauth["accessToken"] = new_token
        oauth["refreshToken"] = new_refresh
        oauth["expiresAt"] = now_ms + expires_in * 1000
        creds["claudeAiOauth"] = oauth
        _write_keychain_credentials(creds, service)

        return new_token

    return access_token


class HarborBackend:
    """AgentBackend bridging Rigger's protocol to Harbor's container environment.

    Uploads ``.harness/`` to the container, executes the Claude CLI via
    ``environment.exec()``, and parses the result into a ``TaskResult``.
    """

    def __init__(
        self,
        environment: object,
        model_name: str | None = None,
        *,
        max_turns: int | None = 30,
        max_thinking_tokens: int | None = None,
    ) -> None:
        self._env = environment
        self._model_name = model_name
        self._max_turns = max_turns
        self._max_thinking_tokens = max_thinking_tokens

    def _build_env_vars(self) -> dict[str, str]:
        """Build environment variables for Claude CLI, following Harbor patterns."""
        env: dict[str, str] = {
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or "",
            "CLAUDE_CODE_OAUTH_TOKEN": _get_oauth_token(),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "IS_SANDBOX": "1",
            "CLAUDE_CONFIG_DIR": "/tmp/claude-config",  # noqa: S108
        }

        if self._model_name:
            name = self._model_name
            if "/" in name:
                name = name.split("/", 1)[-1]
            env["ANTHROPIC_MODEL"] = name

        if self._max_thinking_tokens is not None:
            env["MAX_THINKING_TOKENS"] = str(self._max_thinking_tokens)
        elif "MAX_THINKING_TOKENS" in os.environ:
            env["MAX_THINKING_TOKENS"] = os.environ["MAX_THINKING_TOKENS"]

        return {k: v for k, v in env.items() if v}

    async def execute(self, project_root: Path) -> TaskResult:
        """Execute Claude CLI inside the Harbor container.

        1. Read current task from local ``.harness/``
        2. Upload ``.harness/`` to ``/testbed/.harness/`` in the container
        3. Run setup (create config dirs)
        4. Run Claude CLI with the task instruction
        5. Detect changes via ``git diff --stat``
        6. Return ``TaskResult``
        """
        task = read_current_task(project_root)
        if task is None:
            return TaskResult(
                task_id="unknown",
                status="error",
                metadata={"error": "missing_current_task"},
            )

        harness_dir = project_root / ".harness"
        if harness_dir.exists():
            await self._env.upload_dir(harness_dir, "/testbed/.harness")

        env_vars = self._build_env_vars()

        setup_cmd = (
            "mkdir -p $CLAUDE_CONFIG_DIR/debug "
            "$CLAUDE_CONFIG_DIR/projects/-app "
            "$CLAUDE_CONFIG_DIR/shell-snapshots "
            "$CLAUDE_CONFIG_DIR/statsig "
            "$CLAUDE_CONFIG_DIR/todos"
        )
        await self._env.exec(setup_cmd, env=env_vars, cwd="/testbed")

        feedback = self._read_feedback(project_root)
        if feedback:
            prompt = _RETRY_PROMPT.format(
                test_command=feedback.get("test_command", "unknown"),
                test_output=feedback.get("output", "")[-3000:],
                description=task.description,
            )
        else:
            prompt = _FIRST_ATTEMPT_PROMPT.format(description=task.description)
        escaped = shlex.quote(prompt)

        max_turns_flag = ""
        if self._max_turns is not None:
            max_turns_flag = f"--max-turns {self._max_turns} "

        # Export env vars inline — some container runtimes don't
        # propagate the exec env dict to shell-spawned subprocesses.
        exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env_vars.items())
        claude_cmd = (
            f'export {exports} PATH="$HOME/.local/bin:$PATH"; '
            f"claude --verbose --print --permission-mode=bypassPermissions "
            f"--output-format=stream-json "
            f"{max_turns_flag}"
            f"-- {escaped} 2>&1 </dev/null"
        )

        result = await self._env.exec(claude_cmd, env=env_vars, cwd="/testbed")

        diff_result = await self._env.exec(
            "git diff --stat", cwd="/testbed", timeout_sec=30
        )

        has_changes = bool(diff_result.stdout and diff_result.stdout.strip())

        if result.return_code == 0:
            status = "success" if has_changes else "partial"
        else:
            status = "error"

        return TaskResult(
            task_id=task.id,
            status=status,
            metadata={
                "return_code": result.return_code,
                "has_changes": has_changes,
                "diff_stat": (diff_result.stdout or "")[:2000],
                "stdout_tail": (result.stdout or "")[-2000:],
                "stderr": (result.stderr or "")[:2000],
            },
        )

    @staticmethod
    def _read_feedback(project_root: Path) -> dict | None:
        """Read .harness/feedback.json if it exists, return parsed dict or None."""
        feedback_path = project_root / ".harness" / "feedback.json"
        if not feedback_path.exists():
            return None
        try:
            return json.loads(feedback_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
