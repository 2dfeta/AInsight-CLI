"""Tests for ainsight.core.reporter — ReportWriter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ainsight.core.analyzer import AnalysisSession, FileAnalysisResult
from ainsight.core.reporter import ReportWriter, _safe_filename
from ainsight.core.scanner import ScannedFile
from ainsight.utils.config import Config


def _make_result(
    tmp_path: Path,
    rel_path: str = "src/app.py",
    task: str = "explain",
    output: str = "## Overview\nThis is a test.",
    success: bool = True,
) -> FileAnalysisResult:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text("x = 1\n")
    scanned = ScannedFile(
        path=full,
        relative_path=Path(rel_path),
        content="x = 1\n",
        size_bytes=6,
        language="python",
    )
    result = FileAnalysisResult(file=scanned, task=task, success=success)
    result.combined_output = output
    result.elapsed_seconds = 0.5
    result.token_estimate = 10
    return result


class TestSafeFilename:
    @pytest.mark.parametrize("raw,expected_safe", [
        ("src/app.py", "src__app.py"),
        ("src\\app.py", "src__app.py"),
        ("file:name?.py", "file__name__.py"),
    ])
    def test_unsafe_chars_are_replaced(self, raw: str, expected_safe: str) -> None:
        assert _safe_filename(raw) == expected_safe

    def test_safe_name_unchanged(self) -> None:
        assert _safe_filename("app.py") == "app.py"


class TestReportWriterMarkdown:
    @pytest.fixture
    def md_config(self, minimal_config_data: dict, tmp_path: Path) -> Config:
        minimal_config_data["output"]["format"] = "markdown"
        minimal_config_data["output"]["report_dir"] = str(tmp_path / "reports")
        return Config(minimal_config_data)

    def test_creates_report_directory(self, tmp_path: Path, md_config: Config) -> None:
        session = AnalysisSession(task="explain", root_dir=tmp_path)
        session.results = [_make_result(tmp_path)]
        writer = ReportWriter(md_config)
        report_dir = writer.write(session)
        assert report_dir.exists()

    def test_creates_summary_md(self, tmp_path: Path, md_config: Config) -> None:
        session = AnalysisSession(task="explain", root_dir=tmp_path)
        session.results = [_make_result(tmp_path)]
        writer = ReportWriter(md_config)
        report_dir = writer.write(session)
        assert (report_dir / "summary.md").exists()

    def test_summary_md_contains_task(self, tmp_path: Path, md_config: Config) -> None:
        session = AnalysisSession(task="explain", root_dir=tmp_path)
        session.results = [_make_result(tmp_path)]
        writer = ReportWriter(md_config)
        report_dir = writer.write(session)
        content = (report_dir / "summary.md").read_text()
        assert "explain" in content

    def test_no_json_files_in_markdown_mode(self, tmp_path: Path, md_config: Config) -> None:
        session = AnalysisSession(task="explain", root_dir=tmp_path)
        session.results = [_make_result(tmp_path)]
        writer = ReportWriter(md_config)
        report_dir = writer.write(session)
        json_files = list(report_dir.glob("*.json"))
        assert len(json_files) == 0


class TestReportWriterJSON:
    @pytest.fixture
    def json_config(self, minimal_config_data: dict, tmp_path: Path) -> Config:
        minimal_config_data["output"]["format"] = "json"
        minimal_config_data["output"]["report_dir"] = str(tmp_path / "reports")
        return Config(minimal_config_data)

    def test_creates_summary_json(self, tmp_path: Path, json_config: Config) -> None:
        session = AnalysisSession(task="security", root_dir=tmp_path)
        session.results = [_make_result(tmp_path, task="security")]
        writer = ReportWriter(json_config)
        report_dir = writer.write(session)
        assert (report_dir / "summary.json").exists()

    def test_summary_json_is_valid(self, tmp_path: Path, json_config: Config) -> None:
        session = AnalysisSession(task="security", root_dir=tmp_path)
        session.results = [_make_result(tmp_path, task="security")]
        writer = ReportWriter(json_config)
        report_dir = writer.write(session)
        data = json.loads((report_dir / "summary.json").read_text())
        assert data["task"] == "security"
        assert "files" in data
        assert isinstance(data["files"], list)

    def test_no_md_files_in_json_mode(self, tmp_path: Path, json_config: Config) -> None:
        session = AnalysisSession(task="explain", root_dir=tmp_path)
        session.results = [_make_result(tmp_path)]
        writer = ReportWriter(json_config)
        report_dir = writer.write(session)
        md_files = list(report_dir.glob("*.md"))
        assert len(md_files) == 0


class TestReportWriterBoth:
    @pytest.fixture
    def both_config(self, minimal_config_data: dict, tmp_path: Path) -> Config:
        minimal_config_data["output"]["format"] = "both"
        minimal_config_data["output"]["report_dir"] = str(tmp_path / "reports")
        return Config(minimal_config_data)

    def test_creates_both_summary_files(self, tmp_path: Path, both_config: Config) -> None:
        session = AnalysisSession(task="refactor", root_dir=tmp_path)
        session.results = [_make_result(tmp_path, task="refactor")]
        writer = ReportWriter(both_config)
        report_dir = writer.write(session)
        assert (report_dir / "summary.md").exists()
        assert (report_dir / "summary.json").exists()

    def test_failed_result_reflected_in_summary(self, tmp_path: Path, both_config: Config) -> None:
        session = AnalysisSession(task="explain", root_dir=tmp_path)
        session.results = [_make_result(tmp_path, success=False)]
        writer = ReportWriter(both_config)
        report_dir = writer.write(session)
        data = json.loads((report_dir / "summary.json").read_text())
        assert data["failed_files"] == 1
