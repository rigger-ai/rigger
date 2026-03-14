"""Tests for built-in harness templates."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rigger.templates import copy_template, get_template_dir, list_templates


class TestListTemplates:
    def test_returns_sorted_list(self):
        names = list_templates()
        assert names == sorted(names)

    def test_includes_gsd(self):
        assert "gsd" in list_templates()

    def test_includes_openai(self):
        assert "openai" in list_templates()

    def test_excludes_dunder_dirs(self):
        names = list_templates()
        for name in names:
            assert not name.startswith("_")


class TestGetTemplateDir:
    def test_returns_path_with_harness_yaml(self):
        d = get_template_dir("gsd")
        assert (d / "harness.yaml").is_file()

    def test_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="nonexistent"):
            get_template_dir("nonexistent")

    def test_error_lists_available(self):
        with pytest.raises(KeyError, match="gsd"):
            get_template_dir("nonexistent")


class TestCopyTemplate:
    def test_copies_gsd_files(self, tmp_path):
        created = copy_template("gsd", tmp_path)
        assert Path("harness.yaml") in created
        assert Path("tasks.json") in created

    def test_copies_openai_files(self, tmp_path):
        created = copy_template("openai", tmp_path)
        assert Path("harness.yaml") in created
        assert Path("tasks.json") in created
        assert Path("agents_template.md") in created
        assert Path("docs/design.md") in created
        assert Path("docs/conventions.md") in created

    def test_files_exist_on_disk(self, tmp_path):
        copy_template("gsd", tmp_path)
        assert (tmp_path / "harness.yaml").is_file()
        assert (tmp_path / "tasks.json").is_file()

    def test_creates_subdirs(self, tmp_path):
        copy_template("openai", tmp_path)
        assert (tmp_path / "docs").is_dir()
        assert (tmp_path / "docs" / "design.md").is_file()

    def test_unknown_template_raises_key_error(self, tmp_path):
        with pytest.raises(KeyError, match="bogus"):
            copy_template("bogus", tmp_path)

    def test_creates_dest_if_missing(self, tmp_path):
        dest = tmp_path / "nested" / "dir"
        created = copy_template("gsd", dest)
        assert len(created) > 0
        assert dest.is_dir()


class TestTemplateYamlValid:
    """Verify template YAML files parse and have required structure."""

    @pytest.mark.parametrize("name", list_templates())
    def test_harness_yaml_parseable(self, name):
        d = get_template_dir(name)
        raw = yaml.safe_load((d / "harness.yaml").read_text())
        assert isinstance(raw, dict)
        assert "backend" in raw
        assert "task_source" in raw

    @pytest.mark.parametrize("name", list_templates())
    def test_harness_yaml_has_valid_backend_type(self, name):
        d = get_template_dir(name)
        raw = yaml.safe_load((d / "harness.yaml").read_text())
        assert raw["backend"]["type"] == "claude_code"

    @pytest.mark.parametrize("name", list_templates())
    def test_tasks_json_parseable(self, name):
        import json

        d = get_template_dir(name)
        tasks = json.loads((d / "tasks.json").read_text())
        assert isinstance(tasks, list)
        assert len(tasks) > 0
        for task in tasks:
            assert "id" in task
            assert "description" in task


class TestConfigIntegration:
    """Verify templates produce valid HarnessConfig via load_config."""

    @pytest.mark.parametrize("name", list_templates())
    def test_template_loads_as_valid_config(self, name, tmp_path):
        from rigger._config import load_config

        copy_template(name, tmp_path)
        config = load_config(tmp_path / "harness.yaml")
        assert config.backend.type == "claude_code"
        assert config.task_source.type == "file_list"
