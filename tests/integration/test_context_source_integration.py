"""Integration tests for ContextSource implementations against real filesystems."""

from __future__ import annotations

from rigger._provisioner import ContextProvisioner
from rigger.context_sources import FileTreeContextSource, StaticFilesContextSource


def test_file_tree_discovers_directory(git_project):
    src_dir = git_project / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hello')")

    source = FileTreeContextSource(root="src")
    result = source.gather(git_project)

    assert len(result.files) == 1
    assert result.files[0].name == "main.py"


def test_static_files_copies(git_project):
    ext_dir = git_project / "external"
    ext_dir.mkdir()
    (ext_dir / "plan.md").write_text("# Plan\nDo the thing.")

    source = StaticFilesContextSource(
        source="external/plan.md", destination="docs/plan.md"
    )
    result = source.gather(git_project)

    assert len(result.files) >= 1
    assert (git_project / "docs" / "plan.md").exists()


def test_provisioner_aggregates(git_project):
    dir_a = git_project / "alpha"
    dir_a.mkdir()
    (dir_a / "a.txt").write_text("alpha")

    dir_b = git_project / "beta"
    dir_b.mkdir()
    (dir_b / "b.txt").write_text("beta")

    provisioner = ContextProvisioner(
        sources=[
            FileTreeContextSource(root="alpha"),
            FileTreeContextSource(root="beta"),
        ]
    )
    result = provisioner.provision(git_project)

    names = sorted(f.name for f in result.files)
    assert names == ["a.txt", "b.txt"]
    assert len(result.files) == 2
