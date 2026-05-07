"""
Report writer — persists :class:`AnalysisSession` results as Markdown and/or
JSON files to the configured output directory.

Output layout
─────────────
.ainsight_reports/
  security_2024-06-01_14-30-00/
    summary.json
    summary.md
    src__auth.py.md
    src__auth.py.json
    ...
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from ainsight.core.analyzer import AnalysisSession, FileAnalysisResult
from ainsight.utils.config import Config
from ainsight.utils.formatting import print_success, print_info
from ainsight.utils.logging import get_logger

log = get_logger(__name__)

# Characters that are unsafe in filenames
_UNSAFE_CHARS = re.compile(r"[/\\:*?\"<>|]")


def _safe_filename(path: str) -> str:
    return _UNSAFE_CHARS.sub("__", path)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


class ReportWriter:
    """Write analysis results to disk.

    Parameters
    ----------
    config:
        Loaded configuration (determines output dir and format).
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.format = config.output_format.lower()  # "markdown" | "json" | "both"
        self._report_root = config.report_dir

    def write(self, session: AnalysisSession) -> Path:
        """Persist *session* results; return the report directory."""
        ts = _now_str()
        report_dir = self._report_root / f"{session.task}_{ts}"
        report_dir.mkdir(parents=True, exist_ok=True)

        # Per-file reports
        for result in session.results:
            self._write_file_report(result, report_dir)

        # Summary
        summary = self._build_summary(session)
        if self.format in {"json", "both"}:
            (report_dir / "summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
        if self.format in {"markdown", "both"}:
            (report_dir / "summary.md").write_text(
                self._render_summary_md(session, summary), encoding="utf-8"
            )

        print_success(f"Reports saved to: {report_dir}")
        return report_dir

    # ── Per-file ──────────────────────────────────────────────────────────────

    def _write_file_report(self, result: FileAnalysisResult, report_dir: Path) -> None:
        slug = _safe_filename(str(result.file.relative_path))
        content = result.combined_output or (result.error or "No output.")

        if self.format in {"markdown", "both"}:
            md = self._render_file_md(result, content)
            (report_dir / f"{slug}.md").write_text(md, encoding="utf-8")

        if self.format in {"json", "both"}:
            data = {
                "file": str(result.file.relative_path),
                "task": result.task,
                "success": result.success,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "token_estimate": result.token_estimate,
                "output": content,
                "error": result.error,
            }
            (report_dir / f"{slug}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def _render_file_md(self, result: FileAnalysisResult, content: str) -> str:
        provider = self.config.provider
        model = self.config.active_model
        return (
            f"# AInsight — `{result.display_path}`\n\n"
            f"**Task:** `{result.task}`  \n"
            f"**Provider:** `{provider}` / `{model}`  \n"
            f"**Status:** {'✅ OK' if result.success else '❌ FAILED'}  \n"
            f"**Elapsed:** {result.elapsed_seconds:.2f}s  \n"
            f"**Token estimate:** {result.token_estimate}  \n\n"
            "---\n\n"
            f"{content}\n"
        )

    # ── Summary ───────────────────────────────────────────────────────────────

    def _build_summary(self, session: AnalysisSession) -> dict:  # type: ignore[type-arg]
        return {
            "task": session.task,
            "root_dir": str(session.root_dir),
            "provider": self.config.provider,
            "model": self.config.active_model,
            "total_files": session.total_files,
            "failed_files": session.failed_files,
            "elapsed_seconds": round(session.elapsed, 3),
            "files": [r.to_summary_dict() for r in session.results],
        }

    def _render_summary_md(
        self, session: AnalysisSession, summary: dict  # type: ignore[type-arg]
    ) -> str:
        status = "✅ All passed" if session.failed_files == 0 else f"❌ {session.failed_files} failed"
        rows = "\n".join(
            f"| `{r['file']}` | {r['task']} | {'✅' if r['success'] else '❌'} "
            f"| {r['chunks']} | {r['tokens']} |"
            for r in summary["files"]
        )
        return (
            f"# AInsight Analysis Report\n\n"
            f"**Task:** `{session.task}`  \n"
            f"**Root:** `{session.root_dir}`  \n"
            f"**Provider:** `{self.config.provider}` / `{self.config.active_model}`  \n"
            f"**Files analysed:** {session.total_files}  \n"
            f"**Status:** {status}  \n"
            f"**Elapsed:** {session.elapsed:.1f}s  \n\n"
            "---\n\n"
            "## File Summary\n\n"
            "| File | Task | Status | Chunks | Tokens |\n"
            "|------|------|--------|--------|--------|\n"
            f"{rows}\n"
        )
