"""Configuration loader — reads config.yaml and resolves ${ENV_VAR} placeholders."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

# ── Paths where AInsight looks for config ────────────────────────────────────
_DEFAULT_CONFIG_PATHS: list[Path] = [
    Path.home() / ".ainsight" / "config.yaml",
    Path.cwd() / "config.yaml",
]
_ENV_OVERRIDE = "AINSIGHT_CONFIG"

# ── Sentinel for missing values ───────────────────────────────────────────────
_MISSING = object()


def _resolve_env(value: str) -> str:
    """Replace ``${VAR}`` placeholders with environment variable values."""
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replacer(match: re.Match[str]) -> str:
        var = match.group(1)
        resolved = os.environ.get(var, "")
        return resolved

    return pattern.sub(replacer, value)


def _resolve_recursive(obj: Any) -> Any:  # noqa: ANN401
    """Recursively resolve env-var placeholders in strings."""
    if isinstance(obj, str):
        return _resolve_env(obj)
    if isinstance(obj, dict):
        return {k: _resolve_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_recursive(item) for item in obj]
    return obj


class Config:
    """Dot-accessible wrapper around a YAML configuration dictionary."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, *keys: str, default: Any = None) -> Any:  # noqa: ANN401
        """Retrieve a nested value using dot-path keys, e.g. ``get("openai", "model")``."""
        node: Any = self._data
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key, _MISSING)
            if node is _MISSING:
                return default
        return node

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def provider(self) -> str:
        return str(self.get("provider", default="openai"))

    @property
    def active_model(self) -> str:
        p = self.provider
        return str(self.get(p, "model", default="gpt-4o"))

    @property
    def active_api_key(self) -> str:
        p = self.provider
        return str(self.get(p, "api_key", default=""))

    @property
    def active_temperature(self) -> float:
        p = self.provider
        return float(self.get(p, "temperature", default=0.2))

    @property
    def active_max_tokens(self) -> int:
        p = self.provider
        return int(self.get(p, "max_tokens", default=4096))

    @property
    def chunk_size(self) -> int:
        return int(self.get("token_limits", "chunk_size", default=3000))

    @property
    def response_buffer(self) -> int:
        return int(self.get("token_limits", "response_buffer", default=1500))

    @property
    def max_parallel_files(self) -> int:
        return int(self.get("concurrency", "max_parallel_files", default=5))

    @property
    def report_dir(self) -> Path:
        return Path(str(self.get("output", "report_dir", default=".ainsight_reports")))

    @property
    def output_format(self) -> str:
        return str(self.get("output", "format", default="both"))

    @property
    def scanning(self) -> dict[str, Any]:
        return dict(self.get("scanning", default={}))

    def raw(self) -> dict[str, Any]:
        return self._data


def load_config(path: Path | None = None) -> Config:
    """Load, merge, and resolve configuration from YAML files.

    Search order (later values win):
    1. Built-in defaults embedded here.
    2. ``~/.ainsight/config.yaml``
    3. ``./config.yaml``
    4. Path supplied via ``AINSIGHT_CONFIG`` env var.
    5. Explicit *path* argument.
    """
    # ── Built-in defaults ─────────────────────────────────────────────────────
    base_dir = Path(__file__).parent.parent.parent
    default_path = base_dir / "config.yaml"

    merged: dict[str, Any] = {}

    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _load_yaml(p: Path) -> dict[str, Any]:
        if p.exists():
            with p.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return dict(data)
        return {}

    # Layer the configs
    merged = _load_yaml(default_path)
    for candidate in _DEFAULT_CONFIG_PATHS:
        if candidate != default_path:
            merged = _deep_merge(merged, _load_yaml(candidate))

    env_path = os.environ.get(_ENV_OVERRIDE)
    if env_path:
        merged = _deep_merge(merged, _load_yaml(Path(env_path)))

    if path:
        merged = _deep_merge(merged, _load_yaml(path))

    # Resolve env-var placeholders
    resolved = _resolve_recursive(merged)
    return Config(resolved)  # type: ignore[arg-type]
