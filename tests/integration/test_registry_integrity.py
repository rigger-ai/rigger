"""Integration tests for registry integrity — B7."""

from rigger._registry import _build_default_registry

# Minimal constructor args for each (protocol, name) pair.
MINIMAL_PARAMS = {
    ("task_source", "file_list"): {"path": "tasks.json"},
    ("task_source", "linear"): {"team": "TEST"},
    ("task_source", "atomic_issue"): {
        "provider": "github",
        "issue_id": "123",
    },
    ("task_source", "json_stories"): {"path": "stories.json"},
    ("context_source", "file_tree"): {"root": "src"},
    ("context_source", "agents_md"): {"template": "test"},
    ("context_source", "mcp_capability"): {"name": "test"},
    ("context_source", "static_files"): {
        "source": "a.txt",
        "destination": "b.txt",
    },
    ("verifier", "test_suite"): {"command": ["echo"]},
    ("verifier", "lint"): {"command": ["echo"]},
    ("verifier", "ci_status"): {},
    ("verifier", "ratchet"): {"steps": []},
    ("constraint", "tool_allowlist"): {},
    ("constraint", "branch_policy"): {},
    ("state_store", "json_file"): {"path": "state.json"},
    ("state_store", "harness_dir"): {},
    ("entropy_detector", "shell_command"): {"command": "echo hi"},
    ("entropy_detector", "doc_staleness"): {"patterns": ["*.md"]},
    ("workspace_manager", "git_worktree"): {},
    ("workspace_manager", "independent_dir"): {},
    ("workspace_manager", "independent_branch"): {},
    ("backend", "claude_code"): {},
}


def test_all_builtins_instantiate():
    reg = _build_default_registry()

    for (protocol, name), params in MINIMAL_PARAMS.items():
        cls = reg.get(protocol, name)
        assert cls is not None, f"Registry missing {protocol}/{name}"

        # ClaudeCodeBackend requires SDK at runtime; just verify lookup
        if protocol == "backend":
            continue

        instance = cls(**params)
        assert instance is not None, f"Failed to instantiate {protocol}/{name}"


def test_registry_coverage():
    reg = _build_default_registry()

    expected_counts = {
        "task_source": 4,
        "context_source": 4,
        "verifier": 4,
        "constraint": 2,
        "state_store": 2,
        "entropy_detector": 2,
        "workspace_manager": 3,
        "backend": 1,
    }

    for protocol, expected in expected_counts.items():
        available = reg.available(protocol)
        assert len(available) == expected, (
            f"{protocol}: expected {expected}, got {len(available)}: {available}"
        )

    total = sum(expected_counts.values())
    assert total == 22
