"""Harness class — the orchestration loop and step methods.

The Harness composes the 6 dimension plugins (CP, TD, FL, AC, SC, EM)
plus an AgentBackend into a canonical epoch loop. Step methods are
public for custom loops (tf.GradientTape equivalent).

Source: Strawman API v2 §3, Finding 7.8 (loop as Harness.run()).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rigger._lock import acquire_lock, release_lock
from rigger._merge import merge_metadata
from rigger._protocols import (
    AgentBackend,
    Constraint,
    ContextSource,
    EntropyDetector,
    StateStore,
    TaskSource,
    Verifier,
    WorkspaceManager,
)
from rigger._provisioner import ContextProvisioner
from rigger._schema import (
    read_state,
    write_current_task,
    write_entropy_tasks,
    write_state,
)
from rigger._schema import (
    write_constraints as _schema_write_constraints,
)
from rigger._types import (
    Action,
    EpochState,
    MergeResult,
    ProvisionResult,
    Task,
    TaskResult,
    VerifyAction,
    VerifyResult,
)

logger = logging.getLogger(__name__)

# ─── Default stop predicate ─────────────────────────────────


def all_tasks_done(state: EpochState) -> bool:
    """Default stop predicate. Returns True when no pending tasks remain."""
    return not state.pending_tasks


# ─── Callbacks ───────────────────────────────────────────────


@dataclass
class Callbacks:
    """Hook points for the canonical loop.

    Each callback returns ``Action | None``. Returning ``None`` is
    equivalent to ``Action.CONTINUE``.
    """

    on_epoch_start: Callable[[int, EpochState], Action | None] = field(
        default_factory=lambda: lambda epoch, state: None
    )
    on_task_selected: Callable[[Task], Action | None] = field(
        default_factory=lambda: lambda task: None
    )
    on_provision_complete: Callable[[ProvisionResult], Action | None] = field(
        default_factory=lambda: lambda result: None
    )
    on_task_complete: Callable[[TaskResult], Action | None] = field(
        default_factory=lambda: lambda result: None
    )
    on_verify_complete: Callable[[TaskResult, list[VerifyResult]], Action | None] = (
        field(default_factory=lambda: lambda result, vrs: None)
    )
    on_epoch_end: Callable[[int, EpochState], Action | None] = field(
        default_factory=lambda: lambda epoch, state: None
    )
    on_entropy_scan: Callable[[list[Task]], Action | None] = field(
        default_factory=lambda: lambda tasks: None
    )
    on_escalation: Callable[[Task, list[VerifyResult]], None] = field(
        default_factory=lambda: lambda task, results: None
    )


# ─── Harness ─────────────────────────────────────────────────


class Harness:
    """Orchestration loop composing dimension plugins + AgentBackend.

    Constructor wires the plugins; ``run()`` executes the canonical loop;
    step methods are public for custom loops.
    """

    def __init__(
        self,
        project_root: Path,
        backend: AgentBackend,
        task_source: TaskSource,
        context_sources: list[ContextSource] | None = None,
        verifiers: list[Verifier] | None = None,
        constraints: list[Constraint] | None = None,
        state_store: StateStore | None = None,
        entropy_detectors: list[EntropyDetector] | None = None,
        workspace_manager: WorkspaceManager | None = None,
        inject_entropy_tasks: bool = True,
    ) -> None:
        self.project_root = project_root
        self.backend = backend
        self.task_source = task_source
        self._provisioner = ContextProvisioner(sources=list(context_sources or []))
        self.verifiers: list[Verifier] = list(verifiers or [])
        self.constraints: list[Constraint] = list(constraints or [])
        self.state_store = state_store
        self.entropy_detectors: list[EntropyDetector] = list(entropy_detectors or [])
        self.workspace_manager = workspace_manager
        self.inject_entropy_tasks = inject_entropy_tasks
        self._instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

    # ─── Step methods ────────────────────────────────────────

    def load_state(self) -> EpochState:
        """Load state from StateStore if present, else from .harness/state.json."""
        if self.state_store is not None:
            return self.state_store.load(self.project_root)
        return read_state(self.project_root)

    def select_tasks(self, max_count: int = 1) -> list[Task]:
        """Delegate to TaskSource.pending(), sliced to max_count."""
        return self.task_source.pending(self.project_root)[:max_count]

    def provision(self) -> ProvisionResult:
        """Delegate to ContextProvisioner.provision()."""
        return self._provisioner.provision(self.project_root)

    def assign_task(self, task: Task) -> None:
        """Write .harness/current_task.json."""
        write_current_task(self.project_root, task)

    def check_constraints(self) -> list[VerifyResult]:
        """Call each Constraint.check() and return results."""
        return [c.check(self.project_root) for c in self.constraints]

    async def dispatch(self, task: Task) -> TaskResult:
        """Assign task then await backend.execute()."""
        self.assign_task(task)
        return await self.backend.execute(self.project_root)

    def verify(self, result: TaskResult) -> list[VerifyResult]:
        """Call each Verifier.verify() and return results."""
        return [v.verify(self.project_root, result) for v in self.verifiers]

    def persist(self, state: EpochState) -> None:
        """Write .harness/state.json and call StateStore.save() if present."""
        write_state(self.project_root, state)
        if self.state_store is not None:
            self.state_store.save(self.project_root, state)

    def harvest(self, result: TaskResult, project_root: Path) -> TaskResult:
        """Post-process a dispatch result before verification.

        Default implementation is passthrough. Override or replace for
        custom artifact collection, metric computation, or result enrichment.

        Called by ``run()`` and ``run_once()`` between dispatch and verify.

        Args:
            result: TaskResult from dispatch.
            project_root: The project directory.

        Returns:
            Possibly-modified TaskResult.
        """
        return result

    def scan_entropy(self) -> list[Task]:
        """Call each EntropyDetector.scan() and flatten results."""
        tasks: list[Task] = []
        for detector in self.entropy_detectors:
            tasks.extend(detector.scan(self.project_root))
        return tasks

    def write_constraints(
        self,
        project_root: Path | None = None,
        *,
        results: list[VerifyResult] | None = None,
    ) -> None:
        """Merge constraint metadata and write/delete .harness/constraints.json.

        Public step method for custom loops. If *results* are not provided,
        calls ``check_constraints()`` to obtain them.

        Args:
            project_root: Target directory (defaults to ``self.project_root``).
            results: Pre-computed constraint results. When ``None``,
                ``check_constraints()`` is called automatically.
        """
        root = project_root or self.project_root
        if results is not None:
            constraint_results = results
        else:
            constraint_results = self.check_constraints()
        merged = merge_metadata(constraint_results)
        _schema_write_constraints(root, merged)

    @staticmethod
    def _resolve_verify_action(verify_results: list[VerifyResult]) -> VerifyAction:
        """Determine aggregate action from multiple verification results.

        Precedence: BLOCK > ESCALATE > RETRY > ACCEPT.
        No results returns ACCEPT.
        """
        if not verify_results:
            return VerifyAction.ACCEPT
        actions = {vr.action for vr in verify_results}
        if VerifyAction.BLOCK in actions:
            return VerifyAction.BLOCK
        if VerifyAction.ESCALATE in actions:
            return VerifyAction.ESCALATE
        if VerifyAction.RETRY in actions:
            return VerifyAction.RETRY
        return VerifyAction.ACCEPT

    # ─── Parallel dispatch ────────────────────────────────────

    @staticmethod
    def _copy_provisioned_content(
        provision_results: list[ProvisionResult],
        source_root: Path,
        target_root: Path,
    ) -> None:
        """Copy provisioned files from source_root to matching paths in target_root."""
        for pr in provision_results:
            for f in pr.files:
                try:
                    rel = f.relative_to(source_root)
                except ValueError:
                    continue
                dest = target_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

    async def dispatch_parallel(
        self,
        batch: list[Task],
        epoch_state: EpochState,
        callbacks: Callbacks | None = None,
        provision_results: list[ProvisionResult] | None = None,
    ) -> tuple[list[TaskResult], bool]:
        """Dispatch multiple tasks to parallel agents in isolated workspaces.

        Each task runs in its own workspace created by the WorkspaceManager.
        Uses ``asyncio.gather(return_exceptions=True)`` so all agents are
        independent — a failure in one does not cancel others.

        Args:
            batch: Tasks to execute in parallel.
            epoch_state: Current epoch state (for branch naming).
            callbacks: Optional hook points (on_task_complete checked per task).
            provision_results: Pre-computed provision results to copy into worktrees.

        Returns:
            Tuple of (results, halt_requested). Results are in the same order
            as the input batch. halt_requested is True if any callback returned HALT.

        Raises:
            RuntimeError: If no workspace_manager is configured.
        """
        if self.workspace_manager is None:
            msg = "dispatch_parallel requires a workspace_manager"
            raise RuntimeError(msg)

        cb = callbacks or Callbacks()
        wm = self.workspace_manager
        halt_requested = False
        results: list[TaskResult] = []
        worktrees: list[Path | None] = [None] * len(batch)

        # Phase 1: Create worktrees (sequential — filesystem setup)
        live_indices: list[int] = []
        for i, task in enumerate(batch):
            branch = f"rigger/{self._instance_id}/{epoch_state.epoch}/{task.id}"
            try:
                wt = await asyncio.to_thread(wm.create, self.project_root, task, branch)
                worktrees[i] = wt
                live_indices.append(i)
            except Exception as exc:
                logger.warning(
                    "Failed to create workspace for task %s: %s", task.id, exc
                )
                results.append(
                    TaskResult(
                        task_id=task.id,
                        status="error",
                        metadata={"error": str(exc)},
                    )
                )

        if not live_indices:
            return [r for r in results if r.task_id], halt_requested

        # Phase 2: Copy provisioned content into each worktree
        if provision_results:
            for i in live_indices:
                wt = worktrees[i]
                assert wt is not None  # noqa: S101
                self._copy_provisioned_content(provision_results, self.project_root, wt)

        # Phase 3: Write per-worktree .harness/ (task + state)
        for i in live_indices:
            wt = worktrees[i]
            assert wt is not None  # noqa: S101
            write_current_task(wt, batch[i])
            write_state(wt, epoch_state)

        # Phase 4: Dispatch agents via gather
        async def _execute_one(task: Task, worktree: Path) -> TaskResult:
            return await self.backend.execute(worktree)

        coros = [_execute_one(batch[i], worktrees[i]) for i in live_indices]  # type: ignore[arg-type]
        gather_results = await asyncio.gather(*coros, return_exceptions=True)

        # Build ordered results: merge with pre-existing error results
        live_results: list[TaskResult] = []
        for i, raw in zip(live_indices, gather_results, strict=True):
            task = batch[i]
            if isinstance(raw, BaseException):
                tr = TaskResult(
                    task_id=task.id,
                    status="error",
                    metadata={"error": str(raw)},
                )
            else:
                tr = raw
            live_results.append(tr)

            # Check callback
            action = cb.on_task_complete(tr)
            if action is Action.HALT:
                halt_requested = True

        # Phase 5: Verify per-worktree (on successful results)
        for i, tr in zip(live_indices, live_results, strict=True):
            wt = worktrees[i]
            assert wt is not None  # noqa: S101
            if tr.status != "error" and self.verifiers:
                verify_results = [v.verify(wt, tr) for v in self.verifiers]
                if all(vr.passed for vr in verify_results):
                    tr.status = "verified"
                elif any(not vr.passed for vr in verify_results):
                    tr.status = "verification_failed"

        # Phase 6: Merge sequentially (order matters — priority coupling)
        merge_results: list[MergeResult] = []
        for i, tr in zip(live_indices, live_results, strict=True):
            wt = worktrees[i]
            assert wt is not None  # noqa: S101
            if tr.status != "error":
                mr = await asyncio.to_thread(wm.merge, wt, self.project_root)
                merge_results.append(mr)
                if not mr.success:
                    tr.metadata["merge_conflicts"] = mr.conflicts
            else:
                merge_results.append(MergeResult(success=False, worktree_path=wt))

        # Phase 7: Post-merge constraints
        post_results = self.check_constraints()
        for r in post_results:
            if not r.passed:
                logger.info(
                    "dispatch_parallel: post-merge constraint violation: %s",
                    r.message,
                )

        # Phase 8: Cleanup (parallel with sync fallback)
        async def _cleanup_one(wt: Path) -> None:
            try:
                await asyncio.to_thread(wm.cleanup, wt)
            except asyncio.CancelledError:
                wm.cleanup(wt)

        cleanup_coros = [_cleanup_one(wt) for wt in worktrees if wt is not None]
        await asyncio.gather(*cleanup_coros, return_exceptions=True)

        # Combine results: error results from phase 1 + live results
        # Reconstruct in original batch order
        final: list[TaskResult] = []
        error_iter = iter(r for r in results)
        live_iter = iter(live_results)
        for i in range(len(batch)):
            if i in live_indices:
                final.append(next(live_iter))
            else:
                final.append(next(error_iter))

        return final, halt_requested

    # ─── Canonical loop ──────────────────────────────────────

    async def run(
        self,
        max_epochs: int = 1,
        max_retries: int = 3,
        stop_when: Callable[[EpochState], bool] = all_tasks_done,
        callbacks: Callbacks | None = None,
        *,
        force_lock: bool = False,
    ) -> EpochState:
        """Execute the canonical epoch loop.

        Single task per epoch with VerifyAction routing. Returns final
        EpochState. Acquires ``.harness/harness.lock`` for the duration
        of the run.

        Args:
            max_epochs: Maximum number of epochs to execute.
            max_retries: Maximum retries per task on RETRY action.
            stop_when: Predicate checked after each epoch; breaks if True.
            callbacks: Optional hook points for loop control.
            force_lock: Override an existing lock file.

        Returns:
            Final EpochState after loop terminates.

        Raises:
            HarnessAlreadyRunning: If another instance holds the lock.
        """
        lock_info = acquire_lock(self.project_root, force=force_lock)
        try:
            return await self._run_inner(
                max_epochs=max_epochs,
                max_retries=max_retries,
                stop_when=stop_when,
                callbacks=callbacks,
            )
        finally:
            release_lock(self.project_root, lock_info)

    async def _run_inner(
        self,
        max_epochs: int,
        max_retries: int,
        stop_when: Callable[[EpochState], bool],
        callbacks: Callbacks | None,
    ) -> EpochState:
        """Inner loop implementation for ``run()``."""
        cb = callbacks or Callbacks()
        epoch_state = EpochState()

        for epoch in range(1, max_epochs + 1):
            # READ_STATE
            epoch_state = self.load_state()
            epoch_state.epoch = epoch

            action = cb.on_epoch_start(epoch, epoch_state)
            if action is Action.HALT:
                break

            # SELECT_TASK
            tasks = self.select_tasks()
            if not tasks:
                break
            task = tasks[0]

            action = cb.on_task_selected(task)
            if action is Action.HALT:
                break
            if action is Action.SKIP_TASK:
                continue

            # PROVISION
            provision_result = self.provision()

            action = cb.on_provision_complete(provision_result)
            if action is Action.HALT:
                break
            if action is Action.SKIP_TASK:
                continue

            # CHECK_PRE
            pre_results = self.check_constraints()
            if any(not r.passed for r in pre_results):
                logger.warning(
                    "Epoch %d: pre-dispatch constraint check failed — skipping",
                    epoch,
                )
                continue

            # WRITE_CONFIG
            self.write_constraints(results=pre_results)

            # DISPATCH + VERIFY (with retry loop)
            retries = 0
            loop_halted = False

            while True:
                result = await self.dispatch(task)
                result = self.harvest(result, self.project_root)

                action = cb.on_task_complete(result)
                if action is Action.HALT:
                    loop_halted = True
                    break

                # CHECK_POST
                post_results = self.check_constraints()
                for r in post_results:
                    if not r.passed:
                        logger.info(
                            "Epoch %d: post-dispatch constraint violation: %s",
                            epoch,
                            r.message,
                        )

                # VERIFY
                verify_results = self.verify(result)
                verify_action = self._resolve_verify_action(verify_results)

                if verify_results and verify_action is VerifyAction.ACCEPT:
                    result.status = "verified"
                elif verify_results and verify_action is not VerifyAction.ACCEPT:
                    result.status = "verification_failed"

                action = cb.on_verify_complete(result, verify_results)
                if action is Action.HALT:
                    loop_halted = True
                    break

                # Route on VerifyAction
                if verify_action is VerifyAction.ACCEPT:
                    self.task_source.mark_complete(task.id, result)
                    epoch_state.completed_tasks.append(task.id)
                    if task.id in epoch_state.pending_tasks:
                        epoch_state.pending_tasks.remove(task.id)
                    break

                if verify_action is VerifyAction.RETRY:
                    retries += 1
                    if retries > max_retries:
                        logger.warning(
                            "Task %s: max retries (%d) exhausted — blocking",
                            task.id,
                            max_retries,
                        )
                        epoch_state.halted = True
                        epoch_state.halt_reason = "max_retries_exhausted"
                        loop_halted = True
                        break
                    logger.info(
                        "Task %s: retrying (%d/%d)",
                        task.id,
                        retries,
                        max_retries,
                    )
                    continue

                if verify_action is VerifyAction.BLOCK:
                    epoch_state.halted = True
                    epoch_state.halt_reason = "blocked"
                    loop_halted = True
                    break

                if verify_action is VerifyAction.ESCALATE:
                    epoch_state.halted = True
                    epoch_state.halt_reason = "escalation"
                    cb.on_escalation(task, verify_results)
                    loop_halted = True
                    break

            if loop_halted:
                self.persist(epoch_state)
                break

            # PERSIST
            self.persist(epoch_state)

            action = cb.on_epoch_end(epoch, epoch_state)
            if action is Action.HALT:
                break

            # ENTROPY
            entropy_tasks = self.scan_entropy()

            action = cb.on_entropy_scan(entropy_tasks)
            if action is Action.HALT:
                break

            if self.inject_entropy_tasks and entropy_tasks:
                write_entropy_tasks(self.project_root, entropy_tasks)

            # DECIDE
            epoch_state.pending_tasks = [
                t.id for t in self.task_source.pending(self.project_root)
            ]
            if stop_when(epoch_state):
                break

        return epoch_state

    # ─── Single-task mode ────────────────────────────────────

    async def run_once(
        self,
        task: Task,
        callbacks: Callbacks | None = None,
        *,
        force_lock: bool = False,
    ) -> TaskResult:
        """Single-task event-driven mode. No persist/entropy — caller manages state.

        Acquires ``.harness/harness.lock`` for the duration of the run.

        Args:
            task: The task to execute.
            callbacks: Optional hook points.
            force_lock: Override an existing lock file.

        Returns:
            TaskResult after dispatch and verification.

        Raises:
            HarnessAlreadyRunning: If another instance holds the lock.
        """
        lock_info = acquire_lock(self.project_root, force=force_lock)
        try:
            return await self._run_once_inner(task, callbacks)
        finally:
            release_lock(self.project_root, lock_info)

    async def _run_once_inner(
        self,
        task: Task,
        callbacks: Callbacks | None = None,
    ) -> TaskResult:
        """Inner implementation for ``run_once()``."""
        cb = callbacks or Callbacks()

        # PROVISION
        provision_result = self.provision()

        action = cb.on_provision_complete(provision_result)
        if action is Action.HALT:
            return TaskResult(task_id=task.id, status="halted")

        # CHECK_PRE
        pre_results = self.check_constraints()
        if any(not r.passed for r in pre_results):
            return TaskResult(task_id=task.id, status="constraint_violation")

        # WRITE_CONFIG
        self.write_constraints(results=pre_results)

        # DISPATCH
        result = await self.dispatch(task)

        # HARVEST
        result = self.harvest(result, self.project_root)

        # CHECK_POST
        post_results = self.check_constraints()
        for r in post_results:
            if not r.passed:
                logger.info(
                    "run_once: post-dispatch constraint violation: %s",
                    r.message,
                )

        # VERIFY
        verify_results = self.verify(result)
        if verify_results and all(vr.passed for vr in verify_results):
            result.status = "verified"
        elif verify_results and any(not vr.passed for vr in verify_results):
            result.status = "verification_failed"

        return result

    # ─── Sync convenience ────────────────────────────────────

    def run_sync(
        self,
        max_epochs: int = 1,
        max_retries: int = 3,
        stop_when: Callable[[EpochState], bool] = all_tasks_done,
        callbacks: Callbacks | None = None,
        *,
        force_lock: bool = False,
    ) -> EpochState:
        """Synchronous convenience wrapper around ``run()``.

        Args:
            max_epochs: Maximum number of epochs.
            max_retries: Maximum retries per task on RETRY action.
            stop_when: Stop predicate.
            callbacks: Optional hook points.
            force_lock: Override an existing lock file.

        Returns:
            Final EpochState.

        Raises:
            HarnessAlreadyRunning: If another instance holds the lock.
        """
        return asyncio.run(
            self.run(
                max_epochs=max_epochs,
                max_retries=max_retries,
                stop_when=stop_when,
                callbacks=callbacks,
                force_lock=force_lock,
            )
        )
