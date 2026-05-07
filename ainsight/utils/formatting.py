"""Rich-based formatting utilities for consistent terminal output."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from rich import box
from rich.columns import Columns
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ainsight.utils.logging import console


# ── Severity palette ──────────────────────────────────────────────────────────
SEVERITY_COLORS: dict[str, str] = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
    "info": "blue",
    "ok": "green",
}

TASK_ICONS: dict[str, str] = {
    "explain": "💡",
    "security": "🔒",
    "tests": "🧪",
    "refactor": "✨",
}


def print_banner() -> None:
    """Print the AInsight-CLI welcome banner."""
    banner = Text(justify="center")
    banner.append("  ╔═══════════════════════════════════╗\n", style="bold cyan")
    banner.append("  ║  ", style="bold cyan")
    banner.append("⚡ AInsight-CLI", style="bold white")
    banner.append(" v1.0.0          ║\n", style="bold cyan")
    banner.append("  ║  ", style="bold cyan")
    banner.append("AI-Powered Code Intelligence    ", style="dim white")
    banner.append("║\n", style="bold cyan")
    banner.append("  ╚═══════════════════════════════════╝", style="bold cyan")
    console.print(banner)
    console.print()


def print_section(title: str, icon: str = "▶") -> None:
    console.rule(f"[bold cyan]{icon}  {title}[/]")


def print_file_result(
    file_path: Path,
    task: str,
    result: str,
    provider: str,
    model: str,
) -> None:
    """Render a single-file analysis result inside a Rich panel."""
    icon = TASK_ICONS.get(task, "📄")
    title = f"{icon}  [bold]{escape(str(file_path))}[/]  [dim]({task})[/]"
    footer = f"[dim]Provider: {provider}  |  Model: {model}[/]"

    # Syntax-highlight code blocks within result (crude but effective)
    content: Text | Syntax | str = result

    console.print(
        Panel(
            content,
            title=title,
            subtitle=footer,
            border_style="cyan",
            padding=(1, 2),
            expand=True,
        )
    )


def print_summary_table(results: list[dict]) -> None:  # type: ignore[type-arg]
    """Print a summary table after all files are processed."""
    table = Table(
        title="📊  Analysis Summary",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    table.add_column("File", style="dim", no_wrap=True)
    table.add_column("Task", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Chunks", justify="right")
    table.add_column("Tokens Used", justify="right")

    for row in results:
        status = "✅" if row.get("success") else "❌"
        table.add_row(
            escape(row.get("file", "")),
            row.get("task", ""),
            status,
            str(row.get("chunks", 1)),
            str(row.get("tokens", "—")),
        )

    console.print(table)


def print_security_findings(findings: list[dict]) -> None:  # type: ignore[type-arg]
    """Render security findings as a severity-color-coded table."""
    if not findings:
        console.print("[green]✅  No vulnerabilities found.[/]")
        return

    table = Table(
        title="🔒  Security Findings",
        box=box.DOUBLE_EDGE,
        header_style="bold red",
        show_lines=True,
        expand=True,
    )
    table.add_column("Severity", justify="center", width=10)
    table.add_column("File", style="dim")
    table.add_column("Line", justify="right", width=6)
    table.add_column("Issue")
    table.add_column("CWE", width=8)

    for f in findings:
        sev = str(f.get("severity", "info")).lower()
        color = SEVERITY_COLORS.get(sev, "white")
        table.add_row(
            f"[{color}]{sev.upper()}[/{color}]",
            escape(str(f.get("file", ""))),
            str(f.get("line", "?")),
            escape(str(f.get("issue", ""))),
            str(f.get("cwe", "—")),
        )

    console.print(table)


def highlight_code(code: str, language: str = "python") -> None:
    """Print syntax-highlighted code."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def print_error(message: str) -> None:
    console.print(f"[bold red]✗[/] {escape(message)}")


def print_success(message: str) -> None:
    console.print(f"[bold green]✓[/] {escape(message)}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠[/] {escape(message)}")


def print_info(message: str) -> None:
    console.print(f"[bold cyan]ℹ[/] {escape(message)}")
