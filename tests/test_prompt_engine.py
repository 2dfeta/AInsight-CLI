"""Tests for ainsight.core.prompt_engine — PromptEngine."""

from __future__ import annotations

import pytest

from ainsight.core.prompt_engine import PromptEngine, VALID_TASKS
from ainsight.utils.config import Config


SAMPLE_CODE = "def add(a, b):\n    return a + b\n"


class TestPromptEngine:
    @pytest.fixture(autouse=True)
    def engine(self, config: Config) -> None:
        self.engine = PromptEngine(config)

    def test_system_prompt_is_non_empty(self) -> None:
        assert len(self.engine.system_prompt()) > 50

    @pytest.mark.parametrize("task", list(VALID_TASKS))
    def test_render_returns_string_for_all_tasks(self, task: str) -> None:
        result = self.engine.render(
            task=task,
            file_path="src/app.py",
            language="python",
            code=SAMPLE_CODE,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("task", list(VALID_TASKS))
    def test_render_injects_file_path(self, task: str) -> None:
        result = self.engine.render(
            task=task,
            file_path="src/my_module.py",
            language="python",
            code=SAMPLE_CODE,
        )
        assert "src/my_module.py" in result

    @pytest.mark.parametrize("task", list(VALID_TASKS))
    def test_render_injects_code(self, task: str) -> None:
        result = self.engine.render(
            task=task,
            file_path="f.py",
            language="python",
            code=SAMPLE_CODE,
        )
        assert "def add" in result

    def test_render_invalid_task_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown task"):
            self.engine.render(
                task="invalid_task",
                file_path="f.py",
                language="python",
                code=SAMPLE_CODE,
            )

    def test_render_includes_chunk_info_when_provided(self) -> None:
        result = self.engine.render(
            task="explain",
            file_path="f.py",
            language="python",
            code=SAMPLE_CODE,
            chunk_info={"index": 2, "total": 5},
        )
        assert "2" in result
        assert "5" in result

    def test_render_without_chunk_info_has_no_chunk_header(self) -> None:
        result = self.engine.render(
            task="explain",
            file_path="f.py",
            language="python",
            code=SAMPLE_CODE,
            chunk_info=None,
        )
        # The chunk note block should not appear
        assert "chunk" not in result.lower() or "chunk_info" not in result

    def test_valid_tasks_set_contains_expected_tasks(self) -> None:
        assert VALID_TASKS == {"explain", "security", "tests", "refactor"}
