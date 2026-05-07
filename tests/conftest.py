"""Shared pytest fixtures for AInsight-CLI tests."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from ainsight.utils.config import Config


# ── Config fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def minimal_config_data() -> dict:
    return {
        "provider": "openai",
        "openai": {"api_key": "sk-test", "model": "gpt-4o", "temperature": 0.2, "max_tokens": 4096},
        "gemini": {"api_key": "g-test", "model": "gemini-1.5-pro", "temperature": 0.2, "max_tokens": 8192},
        "anthropic": {"api_key": "ant-test", "model": "claude-sonnet-4-20250514", "temperature": 0.2, "max_tokens": 8192},
        "token_limits": {"chunk_size": 3000, "response_buffer": 1500},
        "scanning": {
            "exclude_dirs": ["node_modules", ".git", ".venv", "__pycache__"],
            "include_extensions": [".py", ".js", ".ts"],
            "max_file_size": 524288,
            "max_files": 50,
        },
        "concurrency": {"max_parallel_files": 5},
        "output": {"report_dir": ".ainsight_reports", "format": "both"},
        "prompts": {"explain": None, "security": None, "tests": None, "refactor": None},
    }


@pytest.fixture
def config(minimal_config_data) -> Config:
    return Config(minimal_config_data)


# ── Filesystem fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal fake project structure for scanner tests."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".git").mkdir()

    (tmp_path / "src" / "main.py").write_text(
        textwrap.dedent("""\
            def add(a: int, b: int) -> int:
                return a + b

            def greet(name: str) -> str:
                return f"Hello, {name}!"
        """)
    )
    (tmp_path / "src" / "utils.js").write_text(
        "function add(a, b) { return a + b; }\n"
    )
    (tmp_path / "tests" / "test_main.py").write_text(
        "def test_add():\n    from src.main import add\n    assert add(1, 2) == 3\n"
    )
    (tmp_path / "node_modules" / "package.js").write_text("// should be excluded\n")
    (tmp_path / ".git" / "config").write_text("[core]\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03")

    return tmp_path


@pytest.fixture
def gitignore_project(tmp_path: Path) -> Path:
    """Project with a .gitignore that excludes secrets.py."""
    (tmp_path / ".gitignore").write_text("secrets.py\nbuild/\n")
    (tmp_path / "app.py").write_text("print('hello')\n")
    (tmp_path / "secrets.py").write_text("PASSWORD = 'hunter2'\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.py").write_text("# compiled\n")
    return tmp_path


# ── AI client mock ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ai_client() -> MagicMock:
    client = MagicMock()
    client.complete = AsyncMock(return_value="Mock AI response.")
    client.provider_name = MagicMock(return_value="openai")
    client.model = "gpt-4o"
    return client


# ── Sample source code ────────────────────────────────────────────────────────

SAMPLE_PYTHON = textwrap.dedent("""\
    import sqlite3

    def get_user(username: str) -> dict:
        \"\"\"Fetch user by username.\"\"\"
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        # VULNERABLE: SQL injection
        cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
        row = cursor.fetchone()
        conn.close()
        return {"username": row[0], "email": row[1]} if row else {}
""")

SAMPLE_JS = textwrap.dedent("""\
    function greet(name) {
        document.getElementById('output').innerHTML = 'Hello, ' + name;
    }
""")
