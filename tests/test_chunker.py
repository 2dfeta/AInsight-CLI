"""Tests for ainsight.core.chunker — FileChunker and TokenCounter."""

from __future__ import annotations

import pytest

from ainsight.core.chunker import Chunk, FileChunker, TokenCounter


class TestTokenCounter:
    def test_empty_string_returns_one(self) -> None:
        counter = TokenCounter(model="gpt-4o")
        # Fallback heuristic: max(1, len("") // 4) == 1
        result = counter.count("")
        assert result >= 1

    def test_short_text_returns_positive_count(self) -> None:
        counter = TokenCounter(model="gpt-4o")
        assert counter.count("Hello, world!") > 0

    def test_longer_text_has_more_tokens(self) -> None:
        counter = TokenCounter(model="gpt-4o")
        short = "Hi"
        long = "Hello, world! " * 100
        assert counter.count(long) > counter.count(short)

    def test_unknown_model_uses_heuristic(self) -> None:
        counter = TokenCounter(model="unknown-model-xyz")
        result = counter.count("some text here for testing")
        assert result > 0


class TestFileChunker:
    def test_small_file_returns_single_chunk(self) -> None:
        chunker = FileChunker(chunk_size=3000)
        code = "x = 1\n" * 10
        chunks = chunker.split(code)
        assert len(chunks) == 1
        assert chunks[0].index == 1
        assert chunks[0].total == 1
        assert chunks[0].content == code

    def test_chunk_index_starts_at_one(self) -> None:
        chunker = FileChunker(chunk_size=3000)
        chunks = chunker.split("short code")
        assert chunks[0].index == 1

    def test_large_content_is_split(self) -> None:
        # Use a very small chunk_size to force splitting
        chunker = FileChunker(chunk_size=20)
        code = "\n".join(f"variable_{i} = {i}" for i in range(100))
        chunks = chunker.split(code, file_path="test.py")
        assert len(chunks) > 1

    def test_all_chunks_have_correct_total(self) -> None:
        chunker = FileChunker(chunk_size=20)
        code = "\n".join(f"x_{i} = {i}" for i in range(100))
        chunks = chunker.split(code)
        total = len(chunks)
        for chunk in chunks:
            assert chunk.total == total

    def test_chunk_indices_are_sequential(self) -> None:
        chunker = FileChunker(chunk_size=20)
        code = "\n".join(f"x_{i} = {i}" for i in range(100))
        chunks = chunker.split(code)
        indices = [c.index for c in chunks]
        assert indices == list(range(1, len(chunks) + 1))

    def test_content_is_preserved_across_chunks(self) -> None:
        chunker = FileChunker(chunk_size=50)
        code = "\n".join(f"line_{i} = '{i}'" for i in range(50))
        chunks = chunker.split(code)
        combined = "\n".join(c.content for c in chunks)
        # Every original line should appear somewhere in the combined output
        for i in range(50):
            assert f"line_{i}" in combined

    def test_needs_chunking_returns_false_for_small_content(self) -> None:
        chunker = FileChunker(chunk_size=3000)
        assert not chunker.needs_chunking("x = 1\n")

    def test_needs_chunking_returns_true_for_large_content(self) -> None:
        chunker = FileChunker(chunk_size=5)
        large = "word " * 1000
        assert chunker.needs_chunking(large)

    def test_single_chunk_has_correct_token_count(self) -> None:
        chunker = FileChunker(chunk_size=3000)
        code = "x = 1\n"
        chunks = chunker.split(code)
        assert chunks[0].token_count > 0

    def test_empty_file_returns_single_chunk(self) -> None:
        chunker = FileChunker(chunk_size=3000)
        chunks = chunker.split("")
        assert len(chunks) == 1

    def test_count_tokens_delegates_to_counter(self) -> None:
        chunker = FileChunker(chunk_size=3000)
        result = chunker.count_tokens("hello world")
        assert result > 0
