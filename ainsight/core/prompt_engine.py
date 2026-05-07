"""
Prompt engine — renders Jinja2 templates from the ``prompts/`` directory.

Usage
─────
    engine = PromptEngine(config)
    user_prompt = engine.render("security", file_path="src/auth.py",
                                language="python", code=source_code)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from ainsight.utils.config import Config
from ainsight.utils.logging import get_logger

log = get_logger(__name__)

# Directory containing built-in prompt templates
_BUILTIN_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# System-level persona injected for all tasks
_SYSTEM_PROMPT = (
    "You are AInsight, an elite AI code intelligence assistant. "
    "You produce structured, actionable, developer-focused analysis. "
    "Be precise, concise, and avoid generic advice. "
    "Always ground your findings in the actual code provided."
)

VALID_TASKS = {"explain", "security", "tests", "refactor"}


class PromptEngine:
    """Render Jinja2 prompt templates for AInsight analysis tasks.

    Parameters
    ----------
    config:
        Loaded configuration. Used to resolve custom template overrides.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._env = self._build_env()

    def _build_env(self) -> Environment:
        # Allow user overrides from config; fall back to built-ins
        search_paths: list[str] = [str(_BUILTIN_PROMPTS_DIR)]

        user_prompt_dir = self.config.get("prompts", "custom_dir")
        if user_prompt_dir and Path(user_prompt_dir).is_dir():
            search_paths.insert(0, str(user_prompt_dir))

        return Environment(
            loader=FileSystemLoader(search_paths),
            autoescape=select_autoescape([]),  # No HTML escaping for code prompts
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def render(
        self,
        task: str,
        file_path: str,
        language: str,
        code: str,
        chunk_info: dict[str, int] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Render the prompt template for *task*.

        Parameters
        ----------
        task:
            One of ``explain``, ``security``, ``tests``, ``refactor``.
        file_path:
            Relative path of the source file (for display in the prompt).
        language:
            Programming language identifier (e.g. ``python``).
        code:
            Source code content to analyse.
        chunk_info:
            Optional dict with ``index`` and ``total`` keys for multi-chunk files.
        extra:
            Extra template variables.

        Returns
        -------
        str
            Rendered prompt string ready to send to the LLM.
        """
        if task not in VALID_TASKS:
            raise ValueError(f"Unknown task '{task}'. Valid: {VALID_TASKS}")

        # Allow per-task template override via config
        override_path = self.config.get("prompts", task)
        template_name: str
        if override_path and Path(override_path).exists():
            # Absolute override: temporarily load from its parent dir
            p = Path(override_path)
            tmp_env = Environment(
                loader=FileSystemLoader(str(p.parent)),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            tpl = tmp_env.get_template(p.name)
        else:
            template_name = f"{task}.j2"
            try:
                tpl = self._env.get_template(template_name)
            except TemplateNotFound:
                log.error("Template not found: %s — using raw code passthrough.", template_name)
                return code

        context: dict[str, Any] = {
            "file_path": file_path,
            "language": language,
            "code": code,
            "chunk_info": chunk_info,
            **(extra or {}),
        }
        return tpl.render(**context)
