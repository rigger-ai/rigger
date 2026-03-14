# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - 2026-03-14

### Added

- **Phase 2 — Protocol & Loop Fixes**
  - `VerifyAction` routing in the epoch loop (RETRY_TASK, BLOCK, ESCALATE, SKIP_TASK)
  - Conditional `mark_complete` — only called on ACCEPT
  - `EntropyDetector.scan()` integration with injectable entropy tasks
  - `IndependentBranchManager` workspace manager
  - Entropy task filesystem protocol (`tasks_{ts}_{uuid}.json` partitioned files)

- **Phase 3 — Built-in Implementations (18 classes)**
  - Task sources: `FileListTaskSource`, `LinearTaskSource`, `AtomicIssueTaskSource`, `JsonStoriesTaskSource`
  - Context sources: `FileTreeContextSource`, `AgentsMdContextSource`, `McpCapabilityContextSource`, `StaticFilesContextSource`
  - Verifiers: `TestSuiteVerifier`, `LintVerifier`, `CiStatusVerifier`, `RatchetVerifier`
  - Constraints: `ToolAllowlistConstraint`, `BranchPolicyConstraint`
  - State stores: `JsonFileStateStore`, `HarnessDirStateStore`
  - Entropy detectors: `ShellCommandEntropyDetector`, `DocStalenessEntropyDetector`

- **Phase 4 — Declarative Layer**
  - `Registry` with plugin discovery via `importlib.metadata` entry points
  - YAML config loader (`load_config`, `build_harness`) with `${ENV_VAR}` interpolation
  - `harness.lock` mechanism to prevent concurrent harness runs
  - CLI: `rigger run`, `rigger status`, `rigger init` (with `--template` and `--list-templates`)
  - Built-in templates: `gsd` (minimal get-shit-done) and `openai` (multi-agent)

- **Harbor integration** (optional `harbor` dependency group)
- 663 tests (up from 283)

## [0.0.1] - 2026-03-04

### Added

- Core framework: `Harness` class with canonical epoch loop, `run()`, `run_once()`, `run_sync()`
- 6 dimension protocols: `TaskSource`, `ContextSource`, `Verifier`, `Constraint`, `StateStore`, `EntropyDetector`
- Infrastructure protocols: `AgentBackend`, `WorkspaceManager`
- Shared types: `Task`, `TaskResult`, `EpochState`, `ProvisionResult`, `VerifyResult`, `VerifyAction`, `Action`, `MergeResult`
- `ContextProvisioner` with fail-open aggregation and `CriticalSource` fail-stop wrapper
- `.harness/` bilateral filesystem protocol with atomic read/write utilities
- Metadata merge algorithm (restrictive, additive, scalar-min families)
- `ClaudeCodeBackend` — first `AgentBackend` implementation (Claude Agent SDK)
- `GitWorktreeManager` and `IndependentDirManager` for parallel workspace isolation
- Parallel dispatch via `asyncio.gather(return_exceptions=True)`
- Step methods for custom loop composition
- `Callbacks` dataclass for loop lifecycle hooks
- 283 tests
