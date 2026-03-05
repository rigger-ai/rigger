# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
