#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# AInsight-CLI — Quick Setup Script
# ─────────────────────────────────────────────────────────────
set -euo pipefail

BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info()    { echo -e "${CYAN}ℹ  $*${RESET}"; }
success() { echo -e "${GREEN}✓  $*${RESET}"; }
warning() { echo -e "${YELLOW}⚠  $*${RESET}"; }
error()   { echo -e "${RED}✗  $*${RESET}" >&2; exit 1; }

echo -e "${BOLD}${CYAN}"
echo "  ╔════════════════════════════════════╗"
echo "  ║   ⚡ AInsight-CLI Setup             ║"
echo "  ╚════════════════════════════════════╝"
echo -e "${RESET}"

# ── Python version check ─────────────────────────────────────
PYTHON=$(command -v python3 || command -v python || error "Python 3.11+ required")
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python version: $PY_VERSION"
if [[ $(echo "$PY_VERSION < 3.11" | bc -l) == "1" ]]; then
    error "Python 3.11+ required (found $PY_VERSION)"
fi

# ── Poetry check ─────────────────────────────────────────────
if command -v poetry &>/dev/null; then
    info "Poetry detected — using Poetry."
    poetry install
    success "Dependencies installed via Poetry."
    ACTIVATE_CMD="poetry run ainsight"
else
    warning "Poetry not found — falling back to pip + venv."
    $PYTHON -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -e ".[dev]" -q 2>/dev/null || pip install \
        typer rich httpx pyyaml pathspec openai google-generativeai \
        anthropic tiktoken jinja2 aiofiles tenacity pygments anyio -q
    pip install pytest pytest-asyncio pytest-cov -q
    success "Dependencies installed in .venv."
    ACTIVATE_CMD="source .venv/bin/activate && ainsight"
fi

# ── Config setup ──────────────────────────────────────────────
if [[ ! -f ~/.ainsight/config.yaml ]]; then
    mkdir -p ~/.ainsight
    cp config.yaml ~/.ainsight/config.yaml
    success "Config copied to ~/.ainsight/config.yaml"
    warning "Edit ~/.ainsight/config.yaml and add your API keys!"
else
    info "Config already exists at ~/.ainsight/config.yaml — skipping."
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
success "AInsight-CLI is ready!"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. Add your API key to ~/.ainsight/config.yaml"
echo -e "  2. Run: ${CYAN}${ACTIVATE_CMD} scan /path/to/project${RESET}"
echo -e "  3. Run: ${CYAN}${ACTIVATE_CMD} security /path/to/project${RESET}"
echo ""
