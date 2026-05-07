"""
Token-aware chunker — splits source-code content that exceeds the model's
context window into manageable pieces.

Strategy
────────
1. Try to keep logical blocks together (class / function boundaries).
2. Fall back to line-based splitting when no clear boundary is found.
3. Provide a summary header for each chunk so the model has context.

Token counting uses ``tiktoken`` for OpenAI-compatible models; a simple
word-count heuristic is used as a fallback for other providers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

from ainsight.utils.logging import get_logger

log = get_logger(__name__)

# Best-effort tokeniser model map
_MODEL_TO_ENCODING: dict[str, str] = {
    "gpt-4o": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
}
_DEFAULT_ENCODING = "cl100k_base"


@dataclass
class Chunk:
    """A single chunk of source code ready to send to the LLM."""

    index: int           # 1-based
    total: int           # total number of chunks for this file
    content: str         # actual source text
    token_count: int


class TokenCounter:
    """Estimate token counts for a given model."""

    def __init__(self, model: str = "gpt-4o") -> None:
        self._model = model
        self._encoder = None

        if _TIKTOKEN_AVAILABLE:
            encoding_name = _MODEL_TO_ENCODING.get(model, _DEFAULT_ENCODING)
            try:
                self._encoder = tiktoken.get_encoding(encoding_name)
            except Exception:
                log.debug("tiktoken encoding '%s' not found; using heuristic.", encoding_name)

    def count(self, text: str) -> int:
        """Return approximate token count for *text*."""
        if self._encoder is not None:
            return len(self._encoder.encode(text))
        # Heuristic: 1 token ≈ 0.75 words ≈ 4 characters
        return max(1, len(text) // 4)


# ── Logical boundary detection ────────────────────────────────────────────────
# Patterns that indicate a "good" split point (start of a top-level construct)
_BOUNDARY_PATTERNS: list[re.Pattern[str]] = [
    # Python top-level class / function
    re.compile(r"^class\s+\w+", re.MULTILINE),
    re.compile(r"^def\s+\w+", re.MULTILINE),
    re.compile(r"^async\s+def\s+\w+", re.MULTILINE),
    # JS/TS function / class
    re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+", re.MULTILINE),
    re.compile(r"^(?:export\s+)?(?:default\s+)?class\s+\w+", re.MULTILINE),
    # Go function
    re.compile(r"^func\s+\w+", re.MULTILINE),
    # Java / C# method / class
    re.compile(r"^\s*(?:public|private|protected|internal|static).*?\{", re.MULTILINE),
]


def _find_boundary_before(lines: list[str], target_line: int) -> int:
    """
    Walk backwards from *target_line* to find the nearest logical boundary line.
    Returns the boundary line index or *target_line* if none found.
    """
    window = min(target_line, 100)
    for i in range(target_line, max(0, target_line - window), -1):
        line = lines[i]
        for pattern in _BOUNDARY_PATTERNS:
            if pattern.match(line):
                return i
    return target_line


class FileChunker:
    """Split file content into LLM-sized chunks.

    Parameters
    ----------
    chunk_size:
        Target token count per chunk (from config).
    model:
        Model name used to select the correct tokeniser.
    """

    def __init__(self, chunk_size: int = 3000, model: str = "gpt-4o") -> None:
        self.chunk_size = chunk_size
        self._counter = TokenCounter(model=model)

    def needs_chunking(self, content: str) -> bool:
        return self._counter.count(content) > self.chunk_size

    def split(self, content: str, file_path: str = "<file>") -> list[Chunk]:
        """Split *content* into a list of :class:`Chunk` objects.

        If the content fits in one chunk, a single-element list is returned.
        """
        total_tokens = self._counter.count(content)

        if total_tokens <= self.chunk_size:
            return [Chunk(index=1, total=1, content=content, token_count=total_tokens)]

        log.debug(
            "%s: %d tokens > chunk_size %d — splitting.",
            file_path,
            total_tokens,
            self.chunk_size,
        )

        lines = content.splitlines()
        chunks: list[Chunk] = []
        current_lines: list[str] = []
        current_tokens = 0

        for i, line in enumerate(lines):
            line_tokens = self._counter.count(line + "\n")

            if current_tokens + line_tokens > self.chunk_size and current_lines:
                # Try to find a clean boundary
                boundary = _find_boundary_before(lines, i)
                if boundary > len(current_lines):
                    # Include lines up to boundary
                    extra = lines[len(current_lines) : boundary]
                    current_lines.extend(extra)

                chunk_text = "\n".join(current_lines)
                chunks.append(
                    Chunk(
                        index=len(chunks) + 1,
                        total=0,  # filled in post
                        content=chunk_text,
                        token_count=self._counter.count(chunk_text),
                    )
                )
                current_lines = []
                current_tokens = 0

            current_lines.append(line)
            current_tokens += line_tokens

        # Last chunk
        if current_lines:
            chunk_text = "\n".join(current_lines)
            chunks.append(
                Chunk(
                    index=len(chunks) + 1,
                    total=0,
                    content=chunk_text,
                    token_count=self._counter.count(chunk_text),
                )
            )

        # Back-fill total
        total = len(chunks)
        for c in chunks:
            c.total = total

        log.debug("Split into %d chunks.", total)
        return chunks

    def count_tokens(self, text: str) -> int:
        return self._counter.count(text)
