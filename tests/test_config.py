"""Tests for ainsight.utils.config — Config and load_config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from ainsight.utils.config import Config, _resolve_env, load_config


class TestResolveEnv:
    def test_resolves_existing_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_KEY", "abc123")
        result = _resolve_env("${MY_KEY}")
        assert result == "abc123"

    def test_missing_env_var_returns_empty_string(self) -> None:
        result = _resolve_env("${NONEXISTENT_VAR_XYZ_123}")
        assert result == ""

    def test_no_placeholder_returns_unchanged(self) -> None:
        assert _resolve_env("plain_value") == "plain_value"

    def test_multiple_placeholders_in_one_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("A", "hello")
        monkeypatch.setenv("B", "world")
        result = _resolve_env("${A} ${B}")
        assert result == "hello world"


class TestConfig:
    def test_provider_property(self, config: Config) -> None:
        assert config.provider == "openai"

    def test_active_model_for_openai(self, config: Config) -> None:
        assert config.active_model == "gpt-4o"

    def test_active_api_key_for_openai(self, config: Config) -> None:
        assert config.active_api_key == "sk-test"

    def test_active_temperature(self, config: Config) -> None:
        assert config.active_temperature == pytest.approx(0.2)

    def test_active_max_tokens(self, config: Config) -> None:
        assert config.active_max_tokens == 4096

    def test_chunk_size(self, config: Config) -> None:
        assert config.chunk_size == 3000

    def test_response_buffer(self, config: Config) -> None:
        assert config.response_buffer == 1500

    def test_max_parallel_files(self, config: Config) -> None:
        assert config.max_parallel_files == 5

    def test_report_dir(self, config: Config) -> None:
        assert config.report_dir == Path(".ainsight_reports")

    def test_output_format(self, config: Config) -> None:
        assert config.output_format == "both"

    def test_get_nested_value(self, config: Config) -> None:
        assert config.get("openai", "model") == "gpt-4o"

    def test_get_returns_default_for_missing_key(self, config: Config) -> None:
        result = config.get("nonexistent", "key", default="fallback")
        assert result == "fallback"

    def test_get_returns_default_for_non_dict_node(self, config: Config) -> None:
        # "openai.model" is a string, not a dict; asking deeper returns default
        result = config.get("openai", "model", "nested", default="x")
        assert result == "x"

    def test_contains_top_level_key(self, config: Config) -> None:
        assert "openai" in config
        assert "nonexistent" not in config

    def test_getitem(self, config: Config) -> None:
        assert config["provider"] == "openai"

    def test_scanning_property_returns_dict(self, config: Config) -> None:
        scanning = config.scanning
        assert isinstance(scanning, dict)
        assert "exclude_dirs" in scanning

    def test_raw_returns_full_dict(self, config: Config) -> None:
        raw = config.raw()
        assert isinstance(raw, dict)
        assert "provider" in raw

    def test_anthropic_provider_returns_correct_model(
        self, minimal_config_data: dict
    ) -> None:
        minimal_config_data["provider"] = "anthropic"
        cfg = Config(minimal_config_data)
        assert cfg.active_model == "claude-sonnet-4-20250514"
        assert cfg.active_api_key == "ant-test"


class TestLoadConfig:
    def test_loads_from_explicit_path(self, tmp_path: Path) -> None:
        cfg_data = {
            "provider": "gemini",
            "gemini": {"api_key": "g-key", "model": "gemini-pro", "temperature": 0.5, "max_tokens": 1000},
        }
        cfg_file = tmp_path / "test_config.yaml"
        cfg_file.write_text(yaml.dump(cfg_data))

        cfg = load_config(cfg_file)
        # Will be merged with defaults; provider should be overridden
        assert cfg.provider == "gemini"

    def test_resolves_env_vars_from_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", "sk-from-env")
        cfg_data = {
            "provider": "openai",
            "openai": {
                "api_key": "${TEST_OPENAI_KEY}",
                "model": "gpt-4o",
                "temperature": 0.2,
                "max_tokens": 100,
            },
        }
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(cfg_data))
        cfg = load_config(cfg_file)
        assert cfg.active_api_key == "sk-from-env"
