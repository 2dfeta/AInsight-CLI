# ⚡ AInsight-CLI

> **AI-powered code intelligence for serious developers.**

AInsight-CLI scans any local project and uses large language models (OpenAI, Gemini, or Anthropic) to perform four types of deep analysis — all from your terminal, with beautiful output and production-grade engineering.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **💡 Explain** | Narrates the logic flow and design decisions of your code |
| **🔒 Security Audit** | Detects OWASP Top 10 vulnerabilities with severity ratings and CWE codes |
| **🧪 Test Generation** | Produces pytest test suites with fixtures, mocks, and edge cases |
| **✨ Refactor** | Applies SOLID + Clean Code principles with a detailed change log |
| **🚀 Async Pipeline** | Processes multiple files concurrently via `asyncio` |
| **🌐 Multi-Provider** | Supports OpenAI (GPT-4o), Google Gemini 1.5 Pro, and Anthropic Claude |
| **📦 Smart Chunking** | Splits large files at logical boundaries — never mid-function |
| **🎨 Rich Terminal UI** | Progress bars, syntax highlighting, severity-coded security tables |
| **📄 Dual Reports** | Saves results as Markdown + JSON for CI/CD integration |
| **🔒 .gitignore Aware** | Respects your project's ignore rules via `pathspec` |

---

## 📁 Project Structure

```
ainsight-cli/
├── ainsight/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── scanner.py        # .gitignore-aware project crawler (pathlib + pathspec)
│   │   ├── chunker.py        # Token-aware file splitter with logical boundary detection
│   │   ├── ai_client.py      # Unified async client: OpenAI | Gemini | Anthropic
│   │   ├── prompt_engine.py  # Jinja2 template renderer
│   │   ├── analyzer.py       # Async orchestration — concurrent file processing
│   │   └── reporter.py       # Markdown + JSON report writer
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py           # Typer CLI: explain / security / tests / refactor / scan
│   ├── prompts/
│   │   ├── explain.j2        # Logic flow prompt template
│   │   ├── security.j2       # Security audit prompt (JSON output)
│   │   ├── tests.j2          # Unit test generation prompt
│   │   └── refactor.j2       # Clean code refactoring prompt
│   └── utils/
│       ├── __init__.py
│       ├── config.py         # YAML config loader with ${ENV_VAR} interpolation
│       ├── logging.py        # Rich-based structured logging
│       └── formatting.py     # Terminal output helpers (tables, panels, banners)
├── tests/
│   ├── conftest.py           # Shared fixtures (config, tmp_project, mock AI client)
│   ├── test_scanner.py       # 15+ scanner tests (gitignore, binary, exclusions)
│   ├── test_chunker.py       # 11+ chunker tests (splitting, token counting)
│   ├── test_config.py        # 20+ config tests (env vars, merging, properties)
│   ├── test_prompt_engine.py # 9+ template rendering tests
│   ├── test_analyzer.py      # Integration tests with mocked AI client
│   └── test_reporter.py      # 15+ report writer tests (MD, JSON, both)
├── scripts/
│   └── install.sh            # Quick setup script
├── config.yaml               # Default configuration template
├── pyproject.toml            # Poetry dependency management
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/ainsight/ainsight-cli
cd ainsight-cli

# Option A — Poetry (recommended)
poetry install

# Option B — pip
pip install -e .

# Option C — automated
bash scripts/install.sh
```

### 2. Configure API Keys

```bash
# Copy the template
mkdir -p ~/.ainsight
cp config.yaml ~/.ainsight/config.yaml

# Edit and add your keys
nano ~/.ainsight/config.yaml
```

Or use environment variables (no config file needed):

```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="AI..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Run Your First Analysis

```bash
# Dry-run: see what files would be scanned
ainsight scan ./my-project

# Explain logic flow
ainsight explain ./my-project

# Security audit
ainsight security ./my-project

# Generate unit tests
ainsight tests ./my-project --file "src/*.py"

# Refactor for clean code
ainsight refactor ./my-project --provider anthropic --model claude-sonnet-4-20250514
```

---

## 📖 CLI Reference

```
Usage: ainsight [OPTIONS] COMMAND [ARGS]...

  ⚡ AInsight-CLI — AI-powered code intelligence.

Options:
  -V, --version  Show version and exit.
  --help         Show this message and exit.

Commands:
  explain   💡 Explain the logic flow of source files
  security  🔒 Run a security audit on source files
  tests     🧪 Generate unit tests for source files
  refactor  ✨ Suggest clean-code refactoring
  scan      📂 Dry-run scan: list files that would be analysed
  config    ⚙️  Show or validate the resolved configuration
```

### Global Options (all analysis commands)

| Option | Short | Description |
|--------|-------|-------------|
| `--config PATH` | `-c` | Path to custom config.yaml |
| `--provider NAME` | `-p` | Override provider: `openai`, `gemini`, `anthropic` |
| `--model NAME` | `-m` | Override model name |
| `--file PATTERN` | `-f` | Restrict to specific files (repeatable glob) |
| `--output DIR` | `-o` | Override report output directory |
| `--no-report` | | Skip writing report files |
| `--verbose` | `-v` | Enable debug logging |

---

## ⚙️ Configuration

The `config.yaml` supports full `${ENV_VAR}` interpolation:

```yaml
provider: openai          # openai | gemini | anthropic

openai:
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4o"
  temperature: 0.2
  max_tokens: 4096

token_limits:
  chunk_size: 3000        # tokens per chunk before splitting
  response_buffer: 1500

scanning:
  exclude_dirs:
    - node_modules
    - .git
    - .venv
  include_extensions:
    - .py
    - .js
    - .ts
  max_file_size: 524288   # 512 KB
  max_files: 50           # 0 = unlimited

concurrency:
  max_parallel_files: 5   # async workers

output:
  report_dir: ".ainsight_reports"
  format: "both"          # markdown | json | both
```

Config is searched in order (later wins):
1. `~/.ainsight/config.yaml`
2. `./config.yaml`
3. `$AINSIGHT_CONFIG` env var
4. `--config` CLI argument

---

## 🏗️ Architecture

```
CLI (Typer)
    │
    ▼
Analyzer (asyncio + Semaphore)
    ├── ProjectScanner (pathlib + pathspec)
    │       └── .gitignore-aware recursive walk
    ├── FileChunker (tiktoken)
    │       └── Logical boundary detection (class/def/func)
    ├── PromptEngine (Jinja2)
    │       └── explain.j2 / security.j2 / tests.j2 / refactor.j2
    ├── BaseAIClient (tenacity retry)
    │       ├── OpenAIClient (AsyncOpenAI)
    │       ├── GeminiClient (run_in_executor)
    │       └── AnthropicClient (AsyncAnthropic)
    └── ReportWriter
            ├── summary.md / summary.json
            └── <file>.md / <file>.json
```

---

## 🧪 Running Tests

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=ainsight --cov-report=html

# Run specific test file
pytest tests/test_scanner.py -v

# Run with verbose output
pytest -v --tb=short
```

---

## 🔧 Extending AInsight

### Custom Prompt Templates

Override any prompt by pointing to a `.j2` file in `config.yaml`:

```yaml
prompts:
  security: "/path/to/my_security_prompt.j2"
```

Templates receive these variables:
- `{{ file_path }}` — relative file path
- `{{ language }}` — detected language
- `{{ code }}` — source content
- `{{ chunk_info.index }}` / `{{ chunk_info.total }}` — for multi-chunk files

### Adding a New Provider

1. Subclass `BaseAIClient` in `ainsight/core/ai_client.py`
2. Implement `complete(system, user) -> str`
3. Register in the `build_client()` factory dict

---

## 📊 Output Example

```
🔒  Security Findings

┌──────────┬─────────────┬──────┬──────────────────────────────────────┬─────────┐
│ Severity │ File        │ Line │ Issue                                │ CWE     │
├──────────┼─────────────┼──────┼──────────────────────────────────────┼─────────┤
│ CRITICAL │ src/auth.py │ 42   │ SQL Injection via f-string           │ CWE-89  │
│ HIGH     │ src/auth.py │ 67   │ Hardcoded secret key                 │ CWE-798 │
│ MEDIUM   │ src/utils.py│ 15   │ Insecure deserialization (pickle)    │ CWE-502 │
└──────────┴─────────────┴──────┴──────────────────────────────────────┴─────────┘
```

---

## 📜 License

MIT — see [LICENSE](LICENSE).
