# Built-in Components

Rigger ships 22 built-in implementations across all 6 dimensions. All are usable from YAML config via their `type` name, or instantiated directly in Python.

## Task Sources

| Type Name | Class | Description |
|-----------|-------|-------------|
| `file_list` | `FileListTaskSource` | Reads tasks from a JSON file (list of `{id, description}` objects) |
| `json_stories` | `JsonStoriesTaskSource` | Reads user stories in PRD format from a JSON file |
| `linear` | `LinearTaskSource` | Pulls tasks from a Linear project via API |
| `atomic_issue` | `AtomicIssueTaskSource` | Creates tasks from GitHub issues |

### Example YAML

```yaml
task_source:
  type: file_list
  path: tasks.json

# Or with env var interpolation:
task_source:
  type: linear
  team_id: ${LINEAR_TEAM_ID}
  api_key: ${LINEAR_API_KEY}
```

## Context Sources

| Type Name | Class | Description |
|-----------|-------|-------------|
| `file_tree` | `FileTreeContextSource` | Provides a directory listing of the project |
| `agents_md` | `AgentsMdContextSource` | Discovers and provisions `AGENTS.md` files |
| `static_files` | `StaticFilesContextSource` | Provisions specific files by path |
| `mcp_capability` | `McpCapabilityContextSource` | Provisions MCP server capability descriptions |

### Example YAML

```yaml
context_sources:
  - type: file_tree
    root: src/
  - type: agents_md
  - type: static_files
    paths:
      - docs/architecture.md
      - docs/api.md
```

## Verifiers

| Type Name | Class | Description |
|-----------|-------|-------------|
| `test_suite` | `TestSuiteVerifier` | Runs a test command and checks exit code |
| `lint` | `LintVerifier` | Runs a linter command and checks exit code |
| `ci_status` | `CiStatusVerifier` | Checks CI pipeline status via GitHub API |
| `ratchet` | `RatchetVerifier` | Ensures a metric never regresses below a threshold |

### Example YAML

```yaml
verifiers:
  - type: test_suite
    command: ["python", "-m", "pytest", "--tb=short", "-q"]
  - type: lint
    command: ruff check .
  - type: ratchet
    metric: coverage
    threshold: 80.0
```

## Constraints

| Type Name | Class | Description |
|-----------|-------|-------------|
| `tool_allowlist` | `ToolAllowlistConstraint` | Restricts agent to specific tools |
| `branch_policy` | `BranchPolicyConstraint` | Enforces branch naming and protects main branches |

### Example YAML

```yaml
constraints:
  - type: tool_allowlist
    tools:
      - Read
      - Edit
      - Bash
  - type: branch_policy
    pattern: "feature/*"
```

## State Stores

| Type Name | Class | Description |
|-----------|-------|-------------|
| `json_file` | `JsonFileStateStore` | Persists state to a JSON file at a custom path |
| `harness_dir` | `HarnessDirStateStore` | Persists state to `.harness/state.json` (default) |

### Example YAML

```yaml
state_store:
  type: json_file
  path: .harness/state.json
```

## Entropy Detectors

| Type Name | Class | Description |
|-----------|-------|-------------|
| `shell_command` | `ShellCommandEntropyDetector` | Runs a shell command and generates tasks from its output |
| `doc_staleness` | `DocStalenessEntropyDetector` | Detects documentation that has drifted from source code |

### Example YAML

```yaml
entropy_detectors:
  - type: shell_command
    command: "git diff --stat HEAD~1"
  - type: doc_staleness
    paths:
      - docs/
```

## Workspace Managers

| Type Name | Class | Description |
|-----------|-------|-------------|
| `git_worktree` | `GitWorktreeManager` | Branch-based isolation via `git worktree` |
| `independent_dir` | `IndependentDirManager` | Full project copy to temp directory |
| `independent_branch` | `IndependentBranchManager` | Branch-based isolation without worktrees |

### Example YAML

```yaml
workspace:
  type: git_worktree
```

## Backends

| Type Name | Class | Description |
|-----------|-------|-------------|
| `claude_code` | `ClaudeCodeBackend` | Wraps the Claude Agent SDK |

### Example YAML

```yaml
backend:
  type: claude_code
  model: claude-sonnet-4-6
  setting_sources:
    - project
```

## Plugin Discovery

Third-party components are discovered via `importlib.metadata` entry points. Register your implementation under the `rigger.<protocol>` group:

```toml
# pyproject.toml
[project.entry-points."rigger.task_source"]
my_source = "my_package:MyTaskSource"
```

Plugins take priority over built-ins (with a warning logged).
