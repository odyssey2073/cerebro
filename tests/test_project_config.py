"""Tests for project_config: name sanitization, collections, registry."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import project_config  # noqa: E402


class TestSanitizeProjectName:
    def test_simple_name(self):
        assert project_config.sanitize_project_name("helix") == "helix"

    def test_spaces_and_uppercase(self):
        assert project_config.sanitize_project_name("My App") == "my_app"

    def test_special_characters(self):
        assert project_config.sanitize_project_name("App (v2)!") == "app_v2"

    def test_edge_underscores_removed(self):
        assert project_config.sanitize_project_name("--app--") == "app"

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError):
            project_config.sanitize_project_name("!!!")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            project_config.sanitize_project_name("")


class TestCollectionFor:
    def test_crb_prefix(self):
        assert project_config.collection_for("helix") == "CRB_helix"

    def test_unsanitized_name(self):
        assert project_config.collection_for("My App") == "CRB_my_app"


class TestAssetsDirFor:
    def test_under_assets_root(self, monkeypatch):
        tmp = Path("/tmp/repo")
        monkeypatch.setattr(project_config, "ASSETS_ROOT", tmp / "assets")
        assert project_config.assets_dir_for("helix") == tmp / "assets" / "helix"

    def test_unsanitized_name(self, monkeypatch):
        tmp = Path("/tmp/repo")
        monkeypatch.setattr(project_config, "ASSETS_ROOT", tmp / "assets")
        assert project_config.assets_dir_for("My App") == tmp / "assets" / "my_app"


class TestResolveProject:
    def test_flag_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("PROJECT", "from_env")
        assert project_config.resolve_project("from_flag") == "from_flag"

    def test_env_used_without_flag(self, monkeypatch):
        monkeypatch.setenv("PROJECT", "from_env")
        assert project_config.resolve_project(None) == "from_env"

    def test_error_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("PROJECT", raising=False)
        with pytest.raises(SystemExit):
            project_config.resolve_project(None)


class TestRegistry:
    def test_roundtrip(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "projects.json"
        monkeypatch.setattr(project_config, "REGISTRY_PATH", reg_path)

        assert project_config.load_registry() == {}

        registry = {"helix": {"docs": ["C:/docs"], "root": "C:/helix"}}
        project_config.save_registry(registry)

        assert project_config.load_registry() == registry
        # file written as valid JSON
        assert json.loads(reg_path.read_text(encoding="utf-8")) == registry

    def test_docs_paths_from_registry(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "projects.json"
        reg_path.write_text(json.dumps({"helix": {"docs": ["C:/docs"]}}), encoding="utf-8")
        monkeypatch.setattr(project_config, "REGISTRY_PATH", reg_path)

        assert project_config.docs_paths_for("helix") == ["C:/docs"]

    def test_docs_paths_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(project_config, "REGISTRY_PATH", tmp_path / "missing.json")
        paths = project_config.docs_paths_for("new_project")
        assert len(paths) == 1
        assert paths[0].endswith(str(Path("projects") / "new_project" / "docs"))
