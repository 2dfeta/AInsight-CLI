"""
Unified async AI client — abstracts OpenAI, Gemini, and Anthropic behind a
single ``complete()`` coroutine with automatic retry logic via ``tenacity``.

Architecture
────────────
BaseAIClient (ABC)
├── OpenAIClient      — uses openai AsyncOpenAI
├── GeminiClient      — uses google.generativeai
└── AnthropicClient   — uses anthropic AsyncAnthropic

Factory function ``build_client(config)`` returns the correct concrete class.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ainsight.utils.config import Config
from ainsight.utils.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


# ── Retry policy ──────────────────────────────────────────────────────────────
def _retry_policy(exc_types: tuple[type[Exception], ...]):  # type: ignore[type-arg]
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(exc_types),
    )


# ── Base client ───────────────────────────────────────────────────────────────
class BaseAIClient(ABC):
    """Abstract base AI client."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.model = config.active_model
        self.temperature = config.active_temperature
        self.max_tokens = config.active_max_tokens

    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt pair and return the model's text response."""
        ...

    @abstractmethod
    def provider_name(self) -> str: ...


# ── OpenAI ───────────────────────────────────────────────────────────────────
class OpenAIClient(BaseAIClient):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        try:
            from openai import AsyncOpenAI, RateLimitError, APIError
        except ImportError as e:
            raise ImportError("Install openai: pip install openai") from e

        self._client = AsyncOpenAI(api_key=config.active_api_key)
        self._rate_limit_error = RateLimitError
        self._api_error = APIError

    def provider_name(self) -> str:
        return "openai"

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        from openai import RateLimitError, APIError

        @_retry_policy((RateLimitError, APIError))
        async def _call() -> str:
            response = await self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            return content or ""

        return await _call()


# ── Gemini ────────────────────────────────────────────────────────────────────
class GeminiClient(BaseAIClient):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ImportError(
                "Install google-generativeai: pip install google-generativeai"
            ) from e

        genai.configure(api_key=config.active_api_key)
        self._genai = genai
        self._model_instance = genai.GenerativeModel(
            model_name=self.model,
            generation_config=genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )

    def provider_name(self) -> str:
        return "gemini"

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        combined = f"{system_prompt}\n\n---\n\n{user_prompt}"

        # google-generativeai doesn't have a native async client yet;
        # run in a thread pool to avoid blocking the event loop.
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._model_instance.generate_content(combined),
        )
        return response.text or ""


# ── Anthropic ─────────────────────────────────────────────────────────────────
class AnthropicClient(BaseAIClient):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        try:
            from anthropic import AsyncAnthropic, RateLimitError, APIError
        except ImportError as e:
            raise ImportError("Install anthropic: pip install anthropic") from e

        self._client = AsyncAnthropic(api_key=config.active_api_key)
        self._RateLimitError = RateLimitError
        self._APIError = APIError

    def provider_name(self) -> str:
        return "anthropic"

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        from anthropic import RateLimitError, APIError

        @_retry_policy((RateLimitError, APIError))
        async def _call() -> str:
            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            block = message.content[0]
            if hasattr(block, "text"):
                return str(block.text)
            return ""

        return await _call()


# ── Factory ───────────────────────────────────────────────────────────────────
def build_client(config: Config) -> BaseAIClient:
    """Return the appropriate :class:`BaseAIClient` for the configured provider."""
    provider = config.provider.lower()
    clients: dict[str, type[BaseAIClient]] = {
        "openai": OpenAIClient,
        "gemini": GeminiClient,
        "anthropic": AnthropicClient,
    }
    if provider not in clients:
        raise ValueError(
            f"Unknown provider '{provider}'. Choose from: {', '.join(clients)}"
        )
    log.debug("Building AI client: provider=%s model=%s", provider, config.active_model)
    return clients[provider](config)
