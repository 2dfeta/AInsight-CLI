"""
Analyzer — the async orchestration core of AInsight-CLI.

Flow
────
1. ``ProjectScanner`` discovers source files.
2. ``FileChunker`` splits large files.
3. ``PromptEngine`` renders task-specific prompts.
4. ``BaseAIClient`` sends prompts concurrently (bounded by semaphore).
5. Results are collected into ``AnalysisResult`` objects.
6. ``ReportWriter`` persists results to disk.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from ainsight.core.ai_client import BaseAIClient, build_client
from ainsight.core.chunker import Chunk, FileChunker
from ainsight.core.prompt_engine import PromptEngine
from ainsight.core.scanner import ProjectScanner, ScannedFile
from ainsight.utils.config import Config
from ainsight.utils.logging import get_logger, console

log = get_logger(__name__)


# ── Result models ─────────────────────────────────────────────────────────────

@dataclass
class ChunkResult:
    chunk_index: int
    chunk_total: int
    raw_response: str
    success: bool
    error: str | None = None


@dataclass
class FileAnalysisResult:
    file: ScannedFile
    task: str
    chunk_results: list[ChunkResult] = field(default_factory=list)
    combined_output: str = ""
    success: bool = True
    error: str | None = None
    elapsed_seconds: float = 0.0
    token_estimate: int = 0

    @property
    def display_path(self) -> str:
        return str(self.file.relative_path)

    def to_summary_dict(self) -> dict:  # type: ignore[type-arg]
        return {
            "file": self.display_path,
            "task": self.task,
            "success": self.success,
            "chunks": len(self.chunk_results),
            "tokens": self.token_estimate,
        }


@dataclass
class AnalysisSession:
    task: str
    root_dir: Path
    results: list[FileAnalysisResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def failed_files(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at


# ── Core analyzer ─────────────────────────────────────────────────────────────

class Analyzer:
    """Orchestrates the full analysis pipeline.

    Parameters
    ----------
    config:
        Loaded configuration.
    task:
        Analysis task: ``explain`` | ``security`` | ``tests`` | ``refactor``.
    root_dir:
        Directory to scan.
    file_filter:
        Optional callable ``(ScannedFile) -> bool`` to restrict files.
    """

    def __init__(
        self,
        config: Config,
        task: str,
        root_dir: Path,
        file_filter: Callable[[ScannedFile], bool] | None = None,
    ) -> None:
        self.config = config
        self.task = task
        self.root_dir = root_dir.resolve()
        self.file_filter = file_filter

        self._client: BaseAIClient = build_client(config)
        self._chunker = FileChunker(
            chunk_size=config.chunk_size,
            model=config.active_model,
        )
        self._prompt_engine = PromptEngine(config)
        self._semaphore = asyncio.Semaphore(config.max_parallel_files)

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run(self) -> AnalysisSession:
        """Scan the project and analyse every file concurrently."""
        scanner = ProjectScanner(self.root_dir, self.config)

        # Collect files eagerly so we can show a progress bar with total
        files = scanner.scan_list()
        if self.file_filter:
            files = [f for f in files if self.file_filter(f)]

        if not files:
            console.print("[yellow]⚠  No eligible source files found.[/]")
            return AnalysisSession(task=self.task, root_dir=self.root_dir)

        session = AnalysisSession(task=self.task, root_dir=self.root_dir)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            prog_task: TaskID = progress.add_task(
                f"[cyan]Analysing ({self.task})…", total=len(files)
            )

            async_tasks = [
                self._analyse_file(f, progress, prog_task) for f in files
            ]
            results: list[FileAnalysisResult] = await asyncio.gather(*async_tasks)

        session.results = results
        return session

    # ── Per-file pipeline ─────────────────────────────────────────────────────

    async def _analyse_file(
        self,
        scanned: ScannedFile,
        progress: Progress,
        prog_task: TaskID,
    ) -> FileAnalysisResult:
        result = FileAnalysisResult(file=scanned, task=self.task)
        t0 = time.time()

        async with self._semaphore:
            try:
                chunks: list[Chunk] = self._chunker.split(
                    scanned.content, file_path=str(scanned.relative_path)
                )
                result.token_estimate = sum(c.token_count for c in chunks)

                chunk_tasks = [self._process_chunk(scanned, chunk) for chunk in chunks]
                chunk_results: list[ChunkResult] = await asyncio.gather(*chunk_tasks)

                result.chunk_results = chunk_results
                result.success = all(cr.success for cr in chunk_results)
                result.combined_output = self._combine_chunks(chunk_results)

            except Exception as exc:
                log.error("Error analysing %s: %s", scanned.relative_path, exc)
                result.success = False
                result.error = str(exc)
            finally:
                result.elapsed_seconds = time.time() - t0
                progress.advance(prog_task)

        return result

    async def _process_chunk(self, scanned: ScannedFile, chunk: Chunk) -> ChunkResult:
        chunk_info = (
            {"index": chunk.index, "total": chunk.total}
            if chunk.total > 1
            else None
        )
        user_prompt = self._prompt_engine.render(
            task=self.task,
            file_path=str(scanned.relative_path),
            language=scanned.language,
            code=chunk.content,
            chunk_info=chunk_info,
        )
        system_prompt = self._prompt_engine.system_prompt()

        try:
            response = await self._client.complete(system_prompt, user_prompt)
            return ChunkResult(
                chunk_index=chunk.index,
                chunk_total=chunk.total,
                raw_response=response,
                success=True,
            )
        except Exception as exc:
            log.error(
                "Chunk %d/%d of %s failed: %s",
                chunk.index,
                chunk.total,
                scanned.relative_path,
                exc,
            )
            return ChunkResult(
                chunk_index=chunk.index,
                chunk_total=chunk.total,
                raw_response="",
                success=False,
                error=str(exc),
            )

    def _combine_chunks(self, results: list[ChunkResult]) -> str:
        if len(results) == 1:
            return results[0].raw_response

        parts: list[str] = []
        for cr in results:
            if cr.success:
                if cr.chunk_total > 1:
                    parts.append(
                        f"<!-- Chunk {cr.chunk_index}/{cr.chunk_total} -->\n{cr.raw_response}"
                    )
                else:
                    parts.append(cr.raw_response)
            else:
                parts.append(f"<!-- Chunk {cr.chunk_index} FAILED: {cr.error} -->")
        return "\n\n---\n\n".join(parts)
