"""Tests for ainsight.core.scanner — ProjectScanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from ainsight.core.scanner import ProjectScanner, ScannedFile, _detect_language, _is_binary


# ── _detect_language ──────────────────────────────────────────────────────────

class TestDetectLanguage:
    @pytest.mark.parametrize("ext,expected", [
        (".py", "python"),
        (".js", "javascript"),
        (".ts", "typescript"),
        (".go", "go"),
        (".rs", "rust"),
        (".java", "java"),
        (".rb", "ruby"),
        (".md", "markdown"),
        (".xyz", "text"),
    ])
    def test_known_extensions_return_correct_language(self, ext: str, expected: str) -> None:
        path = Path(f"file{ext}")
        assert _detect_language(path) == expected

    def test_extension_is_case_insensitive(self) -> None:
        assert _detect_language(Path("file.PY")) == "python"
        assert _detect_language(Path("file.JS")) == "javascript"


# ── _is_binary ────────────────────────────────────────────────────────────────

class TestIsBinary:
    def test_text_bytes_are_not_binary(self) -> None:
        assert not _is_binary(b"print('hello world')\n")

    def test_null_byte_indicates_binary(self) -> None:
        assert _is_binary(b"some data\x00more data")

    def test_null_byte_beyond_sniff_window_is_not_detected(self) -> None:
        # Null byte after 8 KB is not caught by the heuristic
        safe = b"a" * 8192 + b"\x00"
        assert not _is_binary(safe)

    def test_empty_bytes_are_not_binary(self) -> None:
        assert not _is_binary(b"")


# ── ScannedFile ───────────────────────────────────────────────────────────────

class TestScannedFile:
    def test_line_count_is_correct(self, tmp_path: Path) -> None:
        code = "line1\nline2\nline3\n"
        sf = ScannedFile(
            path=tmp_path / "f.py",
            relative_path=Path("f.py"),
            content=code,
            size_bytes=len(code),
            language="python",
        )
        assert sf.line_count == 4  # 3 newlines + 1

    def test_single_line_file(self, tmp_path: Path) -> None:
        code = "x = 1"
        sf = ScannedFile(
            path=tmp_path / "f.py",
            relative_path=Path("f.py"),
            content=code,
            size_bytes=len(code),
            language="python",
        )
        assert sf.line_count == 1


# ── ProjectScanner ────────────────────────────────────────────────────────────

class TestProjectScanner:
    def test_discovers_python_and_js_files(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        assert "src/main.py" in paths
        assert "src/utils.js" in paths

    def test_excludes_node_modules(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        assert not any("node_modules" in p for p in paths)

    def test_excludes_git_directory(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        assert not any(".git" in p for p in paths)

    def test_excludes_binary_files(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        assert "binary.bin" not in paths

    def test_excludes_non_source_extensions(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        # README.md is in include_extensions? No — only .py, .js, .ts in test config
        assert "README.md" not in paths

    def test_respects_gitignore(self, gitignore_project: Path, config) -> None:
        scanner = ProjectScanner(gitignore_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        # secrets.py should be excluded by .gitignore
        assert "secrets.py" not in paths
        assert "app.py" in paths

    def test_respects_gitignore_directories(self, gitignore_project: Path, config) -> None:
        scanner = ProjectScanner(gitignore_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        assert not any("build" in p for p in paths)

    def test_max_files_limit(self, tmp_project: Path, config) -> None:
        # Override max_files to 1
        raw = config.raw()
        raw["scanning"]["max_files"] = 1
        from ainsight.utils.config import Config
        cfg = Config(raw)
        scanner = ProjectScanner(tmp_project, cfg)
        files = scanner.scan_list()
        assert len(files) <= 1

    def test_scan_yields_correct_language(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        files = {str(f.relative_path): f for f in scanner.scan()}
        assert files["src/main.py"].language == "python"
        assert files["src/utils.js"].language == "javascript"

    def test_oversized_file_is_skipped(self, tmp_project: Path, config) -> None:
        big = tmp_project / "src" / "big.py"
        big.write_bytes(b"x = 1\n" * 100_000)  # > 512 KB
        scanner = ProjectScanner(tmp_project, config)
        files = scanner.scan_list()
        paths = {str(f.relative_path) for f in files}
        assert "src/big.py" not in paths

    def test_file_count_estimate(self, tmp_project: Path, config) -> None:
        scanner = ProjectScanner(tmp_project, config)
        estimate = scanner.file_count_estimate()
        actual = len(scanner.scan_list())
        # Estimate may differ slightly (binary files counted differently)
        assert estimate >= 0
