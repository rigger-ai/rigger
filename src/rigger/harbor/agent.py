"""RiggerAgent — Harbor BaseAgent that orchestrates via Rigger's Harness."""

from __future__ import annotations

import tempfile
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

import rigger
from rigger._harness import Harness
from rigger.harbor.backend import HarborBackend
from rigger.harbor.task_source import InstructionTaskSource
from rigger.harbor.verifier import ContainerTestVerifier
from rigger.state_stores import HarnessDirStateStore


class RiggerAgent(BaseAgent):
    """Harbor agent that delegates orchestration to Rigger's Harness.

    When ``test_command`` is provided (via ``--ak test_command=...``), uses
    ``Harness.run()`` with a ``ContainerTestVerifier`` for dispatch+verify
    retry loop. Otherwise falls back to ``Harness.run_once()``.
    """

    def __init__(self, **kwargs: object) -> None:
        self._test_command: str | None = kwargs.pop("test_command", None)
        self._max_retries: int = int(kwargs.pop("max_retries", 2))
        self._max_turns: int = int(kwargs.pop("max_turns", 30))
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the agent name for Harbor."""
        return "rigger"

    def version(self) -> str | None:
        """Return the Rigger framework version."""
        return rigger.__version__

    async def setup(self, environment: BaseEnvironment) -> None:
        """Install Claude CLI in the container via the official installer."""
        install_cmd = (
            "if command -v apt-get > /dev/null 2>&1; then "
            "apt-get update && apt-get install -y curl procps; "
            "elif command -v apk > /dev/null 2>&1; then "
            "apk add --no-cache curl bash procps; "
            "fi && "
            "curl -fsSL https://claude.ai/install.sh | bash"
        )
        result = await environment.exec(install_cmd, timeout_sec=300)
        if result.return_code != 0:
            detail = (result.stderr or "")[:500]
            msg = f"Claude CLI install failed (exit {result.return_code}): {detail}"
            raise RuntimeError(msg)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run a task through Rigger's harness pipeline.

        With ``test_command``: full dispatch+verify retry loop via ``harness.run()``.
        Without: single dispatch via ``harness.run_once()`` (backward compatible).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            task_source = InstructionTaskSource(instruction)
            backend = HarborBackend(
                environment,
                self.model_name,
                max_turns=self._max_turns,
            )
            state_store = HarnessDirStateStore()

            verifiers = []
            if self._test_command:
                verifiers.append(
                    ContainerTestVerifier(
                        environment,
                        self._test_command,
                    )
                )

            harness = Harness(
                project_root,
                backend,
                task_source,
                state_store=state_store,
                verifiers=verifiers,
            )

            if self._test_command:
                state = await harness.run(
                    max_epochs=1,
                    max_retries=self._max_retries,
                    force_lock=True,
                )
                context.metadata = {
                    "rigger_status": "verified" if state.completed_tasks else "failed",
                    "rigger_task_id": state.completed_tasks[0]
                    if state.completed_tasks
                    else "swebench",
                    "rigger_halted": state.halted,
                    "rigger_halt_reason": state.halt_reason,
                }
            else:
                task = task_source.pending(project_root)[0]
                result = await harness.run_once(task, force_lock=True)
                context.metadata = {
                    "rigger_status": result.status,
                    "rigger_task_id": result.task_id,
                    **(result.metadata or {}),
                }
