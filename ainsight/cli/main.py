"""
AInsight-CLI — main Typer application.

Commands
────────
  ainsight explain   <dir>   Explain logic flow
  ainsight security  <dir>   Security audit
  ainsight tests     <dir>   Generate unit tests
  ainsight refactor  <dir>   Clean-code refactoring
  ainsight scan      <dir>   Show discovered files (dry run)
  ainsight config    show    Print resolved configuration
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.markup import escape
from rich.table import Table

from ainsight import __version__
from ainsight.core.analyzer import Analyzer
from ainsight.core.reporter import ReportWriter
from ainsight.core.scanner import ProjectScanner
from ainsight.utils.config import load_config
from ainsight.utils.formatting import (
    console,
    print_banner,
    print_error,
    print_file_result,
    print_info,
    print_section,
    print_security_findings,
    print_summary_table,
    print_success,
    print_warning,
)
from ainsight.utils.logging import set_verbosity

# ── App definition ────────────────────────────────────────────────────────────
app = typer.Typer(
    name="ainsight",
    help="⚡ AInsight-CLI — AI-powered code intelligence.",
    add_completion=True,
    rich_markup_mode="rich",
    no_args_is_help=True,
)

# ── Common option types ───────────────────────────────────────────────────────
DirArg = Annotated[Path, typer.Argument(help="Project root directory to analyse.")]
ConfigOpt = Annotated[
    Optional[Path],
    typer.Option("--config", "-c", help="Path to custom config.yaml.", show_default=False),
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging.")]
OutputOpt = Annotated[
    Optional[Path],
    typer.Option("--output", "-o", help="Override report output directory.", show_default=False),
]
FilesOpt = Annotated[
    Optional[list[str]],
    typer.Option(
        "--file", "-f",
        help="Restrict analysis to specific file(s) (relative glob, repeatable).",
        show_default=False,
    ),
]
ProviderOpt = Annotated[
    Optional[str],
    typer.Option("--provider", "-p", help="Override AI provider (openai|gemini|anthropic)."),
]
ModelOpt = Annotated[
    Optional[str],
    typer.Option("--model", "-m", help="Override model name."),
]
NoReportOpt = Annotated[bool, typer.Option("--no-report", help="Skip writing report files.")]


# ── Shared setup helper ───────────────────────────────────────────────────────
def _setup(
    directory: Path,
    config_path: Optional[Path],
    verbose: bool,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    output: Optional[Path] = None,
):  # type: ignore[return]
    """Validate inputs and return a loaded Config."""
    set_verbosity(verbose)

    if not directory.exists():
        print_error(f"Directory not found: {directory}")
        raise typer.Exit(1)
    if not directory.is_dir():
        print_error(f"Not a directory: {directory}")
        raise typer.Exit(1)

    cfg = load_config(config_path)

    # CLI overrides
    raw = cfg.raw()
    if provider:
        raw["provider"] = provider
    if model:
        p = raw.get("provider", "openai")
        raw.setdefault(p, {})["model"] = model  # type: ignore[index]
    if output:
        raw.setdefault("output", {})["report_dir"] = str(output)  # type: ignore[union-attr]

    return cfg


def _file_filter_fn(files: Optional[list[str]]):  # type: ignore[return]
    """Return a filter function for specific file patterns, or None."""
    if not files:
        return None

    import fnmatch

    def _filter(scanned) -> bool:  # type: ignore[return]
        for pattern in files:
            if fnmatch.fnmatch(str(scanned.relative_path), pattern):
                return True
        return False

    return _filter


# ── Generic analysis runner ───────────────────────────────────────────────────
def _run_analysis(
    task: str,
    directory: Path,
    config_path: Optional[Path],
    verbose: bool,
    provider: Optional[str],
    model: Optional[str],
    output: Optional[Path],
    files: Optional[list[str]],
    no_report: bool,
) -> None:
    print_banner()
    print_section(f"Task: {task.upper()}", icon="⚡")

    cfg = _setup(directory, config_path, verbose, provider, model, output)

    print_info(
        f"Provider: [bold]{cfg.provider}[/]  Model: [bold]{cfg.active_model}[/]  "
        f"Dir: [bold]{directory}[/]"
    )

    analyzer = Analyzer(
        config=cfg,
        task=task,
        root_dir=directory,
        file_filter=_file_filter_fn(files),
    )

    try:
        session = asyncio.run(analyzer.run())
    except KeyboardInterrupt:
        print_warning("Analysis interrupted by user.")
        raise typer.Exit(0)
    except Exception as exc:
        print_error(f"Fatal error: {exc}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    # ── Display results ───────────────────────────────────────────────────────
    print_section("Results")
    for result in session.results:
        if task == "security":
            _display_security(result, cfg)
        else:
            print_file_result(
                file_path=result.file.relative_path,
                task=task,
                result=result.combined_output or (result.error or "No output"),
                provider=cfg.provider,
                model=cfg.active_model,
            )

    # ── Summary table ─────────────────────────────────────────────────────────
    print_section("Summary")
    print_summary_table([r.to_summary_dict() for r in session.results])

    # ── Write reports ─────────────────────────────────────────────────────────
    if not no_report:
        writer = ReportWriter(cfg)
        writer.write(session)

    if session.failed_files > 0:
        raise typer.Exit(1)


def _display_security(result, cfg) -> None:  # type: ignore[no-untyped-def]
    """Try to parse JSON security output and render findings table."""
    import json

    raw = result.combined_output
    try:
        # Strip markdown code fences if present
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = "\n".join(stripped.splitlines()[1:])
            stripped = stripped.rstrip("`").strip()
        data = json.loads(stripped)
        findings = data.get("findings", [])
        # Inject file path into each finding
        for f in findings:
            f["file"] = str(result.file.relative_path)
        print_section(f"🔒 {result.display_path}", icon="")
        print_security_findings(findings)
        summary = data.get("summary", "")
        if summary:
            console.print(f"\n[dim]{escape(summary)}[/]\n")
    except (json.JSONDecodeError, AttributeError):
        # Fall back to raw display
        print_file_result(
            file_path=result.file.relative_path,
            task="security",
            result=raw,
            provider=cfg.provider,
            model=cfg.active_model,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Commands
# ══════════════════════════════════════════════════════════════════════════════

@app.command()
def explain(
    directory: DirArg = Path("."),
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    output: OutputOpt = None,
    files: FilesOpt = None,
    no_report: NoReportOpt = False,
) -> None:
    """💡 Explain the logic flow of source files in [cyan]DIRECTORY[/]."""
    _run_analysis("explain", directory, config, verbose, provider, model, output, files, no_report)


@app.command()
def security(
    directory: DirArg = Path("."),
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    output: OutputOpt = None,
    files: FilesOpt = None,
    no_report: NoReportOpt = False,
) -> None:
    """🔒 Run a security audit on source files in [cyan]DIRECTORY[/]."""
    _run_analysis("security", directory, config, verbose, provider, model, output, files, no_report)


@app.command()
def tests(
    directory: DirArg = Path("."),
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    output: OutputOpt = None,
    files: FilesOpt = None,
    no_report: NoReportOpt = False,
) -> None:
    """🧪 Generate unit tests for source files in [cyan]DIRECTORY[/]."""
    _run_analysis("tests", directory, config, verbose, provider, model, output, files, no_report)


@app.command()
def refactor(
    directory: DirArg = Path("."),
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    provider: ProviderOpt = None,
    model: ModelOpt = None,
    output: OutputOpt = None,
    files: FilesOpt = None,
    no_report: NoReportOpt = False,
) -> None:
    """✨ Suggest clean-code refactoring for source files in [cyan]DIRECTORY[/]."""
    _run_analysis("refactor", directory, config, verbose, provider, model, output, files, no_report)


# ── Utility commands ──────────────────────────────────────────────────────────

@app.command()
def scan(
    directory: DirArg = Path("."),
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """📂 Dry-run scan: list all files that would be analysed in [cyan]DIRECTORY[/]."""
    print_banner()
    cfg = _setup(directory, config, verbose)
    scanner = ProjectScanner(directory, cfg)

    table = Table(
        title=f"📂  Discovered Source Files — {directory}",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    table.add_column("File", style="dim")
    table.add_column("Language", justify="center")
    table.add_column("Lines", justify="right")
    table.add_column("Size", justify="right")

    count = 0
    for f in scanner.scan():
        table.add_row(
            str(f.relative_path),
            f.language,
            str(f.line_count),
            f"{f.size_bytes:,} B",
        )
        count += 1

    console.print(table)
    print_info(f"Total: {count} file(s) eligible for analysis.")


@app.command(name="config")
def config_cmd(
    show: Annotated[bool, typer.Option("--show", help="Print resolved configuration.")] = True,
    config: ConfigOpt = None,
) -> None:
    """⚙️  Show or validate the resolved configuration."""
    import yaml

    cfg = load_config(config)
    raw = cfg.raw()

    # Redact API keys
    for provider in ("openai", "gemini", "anthropic"):
        if provider in raw and "api_key" in raw[provider]:
            key = raw[provider]["api_key"]
            raw[provider]["api_key"] = key[:6] + "…" if len(key) > 6 else "***"

    console.print("[bold cyan]Resolved Configuration:[/]\n")
    console.print(yaml.dump(raw, default_flow_style=False, allow_unicode=True))


@app.callback(invoke_without_command=True)
def callback(
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Show version and exit.")
    ] = False,
) -> None:
    """⚡ AInsight-CLI — AI-powered code intelligence tool."""
    if version:
        console.print(f"[bold cyan]AInsight-CLI[/] version [bold]{__version__}[/]")
        raise typer.Exit()


if __name__ == "__main__":
    app()
