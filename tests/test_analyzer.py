"""Tests for ainsight.core.analyzer — Analyzer (mocked AI client)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ainsight.core.analyzer import Analyzer, AnalysisSession, FileAnalysisResult
from ainsight.core.scanner import ScannedFile
from ainsight.utils.config import Config


SAMPLE_CODE = textwrap.dedent("""\
    def greet(name: str) -> str:
        return f"Hello, {name}!"
""")


@pytest.fixture
def tmp_python_project(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(SAMPLE_CODE)
    return tmp_path


@pytest.fixture
def patched_analyzer(config: Config, tmp_python_project: Path):
    """Analyzer with AI client replaced by a mock."""
    analyzer = Analyzer(config=config, task="explain", root_dir=tmp_python_project)

    mock_client = MagicMock()
    mock_client.complete = AsyncMock(return_value="## Overview\nThis function greets someone.")
    mock_client.provider_name = MagicMock(return_value="openai")
    mock_client.model = "gpt-4o"

    analyzer._client = mock_client
    return analyzer


class TestAnalyzer:
    @pytest.mark.asyncio
    async def test_run_returns_analysis_session(self, patched_analyzer: Analyzer) -> None:
        session = await patched_analyzer.run()
        assert isinstance(session, AnalysisSession)

    @pytest.mark.asyncio
    async def test_session_contains_results(self, patched_analyzer: Analyzer) -> None:
        session = await patched_analyzer.run()
        assert len(session.results) >= 1

    @pytest.mark.asyncio
    async def test_result_is_successful(self, patched_analyzer: Analyzer) -> None:
        session = await patched_analyzer.run()
        for result in session.results:
            assert result.success is True

    @pytest.mark.asyncio
    async def test_result_has_output(self, patched_analyzer: Analyzer) -> None:
        session = await patched_analyzer.run()
        for result in session.results:
            assert "Overview" in result.combined_output

    @pytest.mark.asyncio
    async def test_ai_client_is_called(self, patched_analyzer: Analyzer) -> None:
        session = await patched_analyzer.run()
        assert patched_analyzer._client.complete.called

    @pytest.mark.asyncio
    async def test_file_filter_restricts_results(
        self, config: Config, tmp_python_project: Path
    ) -> None:
        # Add a second file
        (tmp_python_project / "other.py").write_text("x = 1\n")

        def only_app(scanned: ScannedFile) -> bool:
            return scanned.relative_path.name == "app.py"

        analyzer = Analyzer(
            config=config,
            task="explain",
            root_dir=tmp_python_project,
            file_filter=only_app,
        )
        mock_client = MagicMock()
        mock_client.complete = AsyncMock(return_value="ok")
        analyzer._client = mock_client

        session = await analyzer.run()
        assert all(r.file.relative_path.name == "app.py" for r in session.results)

    @pytest.mark.asyncio
    async def test_failed_ai_call_marks_result_failed(
        self, config: Config, tmp_python_project: Path
    ) -> None:
        analyzer = Analyzer(config=config, task="explain", root_dir=tmp_python_project)
        mock_client = MagicMock()
        mock_client.complete = AsyncMock(side_effect=RuntimeError("API down"))
        analyzer._client = mock_client

        session = await analyzer.run()
        assert any(not r.success for r in session.results)

    @pytest.mark.asyncio
    async def test_empty_directory_returns_empty_session(
        self, config: Config, tmp_path: Path
    ) -> None:
        analyzer = Analyzer(config=config, task="explain", root_dir=tmp_path)
        session = await analyzer.run()
        assert session.total_files == 0

    def test_session_elapsed_is_positive(self) -> None:
        import time
        session = AnalysisSession(task="explain", root_dir=Path("."))
        time.sleep(0.01)
        assert session.elapsed > 0

    def test_session_failed_files_count(self) -> None:
        from ainsight.core.scanner import ScannedFile
        session = AnalysisSession(task="explain", root_dir=Path("."))
        scanned = ScannedFile(
            path=Path("f.py"),
            relative_path=Path("f.py"),
            content="x=1",
            size_bytes=3,
            language="python",
        )
        session.results = [
            FileAnalysisResult(file=scanned, task="explain", success=True),
            FileAnalysisResult(file=scanned, task="explain", success=False),
        ]
        assert session.failed_files == 1
        assert session.total_files == 2
