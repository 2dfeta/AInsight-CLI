"""
Project scanner — crawls a directory, respects .gitignore via pathspec,
and yields source-code files suitable for LLM analysis.

Design notes
────────────
• Uses ``pathlib.Path`` throughout (no ``os.path`` calls).
• Layers multiple ``.gitignore`` files (repo root + sub-dirs).
• Skips binary files via a fast heuristic (null-byte sniff).
• Respects ``scanning.exclude_dirs`` and ``scanning.include_extensions``
  from ``Config``.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pathspec

from ainsight.utils.config import Config
from ainsight.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ScannedFile:
    """Metadata + raw content for a single source file."""

    path: Path
    relative_path: Path
    content: str
    size_bytes: int
    language: str
    line_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.line_count = self.content.count("\n") + 1


# ── Language detection ────────────────────────────────────────────────────────
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".rs": "rust",
    ".kt": "kotlin",
    ".swift": "swift",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
}


def _detect_language(path: Path) -> str:
    return _EXT_TO_LANG.get(path.suffix.lower(), "text")


def _is_binary(content_bytes: bytes) -> bool:
    """Fast binary detection: null bytes in first 8 KB → binary."""
    return b"\x00" in content_bytes[:8192]


def _load_gitignore(directory: Path) -> pathspec.PathSpec | None:
    gi = directory / ".gitignore"
    if gi.exists():
        try:
            patterns = gi.read_text(encoding="utf-8", errors="replace").splitlines()
            return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        except OSError:
            pass
    return None


class ProjectScanner:
    """Crawl *root_dir* and yield :class:`ScannedFile` instances.

    Parameters
    ----------
    root_dir:
        Absolute path to the project root.
    config:
        Loaded :class:`~ainsight.utils.config.Config` instance.
    """

    def __init__(self, root_dir: Path, config: Config) -> None:
        self.root_dir = root_dir.resolve()
        self.config = config
        self._scanning = config.scanning

        self._exclude_dirs: set[str] = set(
            self._scanning.get("exclude_dirs", [])
        )
        self._include_exts: set[str] = {
            ext.lower() for ext in self._scanning.get("include_extensions", [".py"])
        }
        self._max_size: int = int(self._scanning.get("max_file_size", 524288))
        self._max_files: int = int(self._scanning.get("max_files", 0))

        # Build a composite .gitignore spec from the root
        self._gitignore_specs: list[tuple[Path, pathspec.PathSpec]] = []
        self._collect_gitignores(self.root_dir)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _collect_gitignores(self, directory: Path) -> None:
        spec = _load_gitignore(directory)
        if spec:
            self._gitignore_specs.append((directory, spec))

    def _is_ignored(self, path: Path) -> bool:
        """Return True if *path* is ignored by any loaded .gitignore spec."""
        for base, spec in self._gitignore_specs:
            try:
                rel = path.relative_to(base)
            except ValueError:
                continue
            if spec.match_file(str(rel)):
                return True
        return False

    def _should_exclude_dir(self, dir_path: Path) -> bool:
        if dir_path.name in self._exclude_dirs:
            return True
        if dir_path.name.startswith(".") and dir_path.name not in {"."}:
            return True
        return self._is_ignored(dir_path)

    def _read_file(self, path: Path) -> str | None:
        """Read and decode a file; return None if it is binary or unreadable."""
        try:
            raw = path.read_bytes()
        except OSError as exc:
            log.debug("Cannot read %s: %s", path, exc)
            return None

        if _is_binary(raw):
            log.debug("Skipping binary: %s", path)
            return None

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return raw.decode("latin-1")
            except UnicodeDecodeError:
                log.debug("Cannot decode %s", path)
                return None

    # ── Public API ────────────────────────────────────────────────────────────

    def scan(self) -> Iterator[ScannedFile]:
        """Yield :class:`ScannedFile` for every eligible source file."""
        count = 0
        for path in self._walk(self.root_dir):
            if self._max_files and count >= self._max_files:
                log.warning(
                    "Reached max_files limit (%d). Use --max-files to increase.",
                    self._max_files,
                )
                break

            if path.suffix.lower() not in self._include_exts:
                continue
            if path.stat().st_size > self._max_size:
                log.debug("Skipping oversized file: %s", path)
                continue
            if self._is_ignored(path):
                continue

            content = self._read_file(path)
            if content is None:
                continue

            yield ScannedFile(
                path=path,
                relative_path=path.relative_to(self.root_dir),
                content=content,
                size_bytes=path.stat().st_size,
                language=_detect_language(path),
            )
            count += 1

    def _walk(self, directory: Path) -> Iterator[Path]:
        """Recursive DFS walk that prunes excluded directories."""
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_dir(), p.name))
        except PermissionError:
            return

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if self._should_exclude_dir(entry):
                    log.debug("Excluding directory: %s", entry.name)
                    continue
                # Load nested .gitignore
                self._collect_gitignores(entry)
                yield from self._walk(entry)
            elif entry.is_file():
                yield entry

    def scan_list(self) -> list[ScannedFile]:
        return list(self.scan())

    def file_count_estimate(self) -> int:
        """Quick count for progress-bar initialisation (does not read files)."""
        count = 0
        for path in self._walk(self.root_dir):
            if path.suffix.lower() in self._include_exts:
                count += 1
        return count
