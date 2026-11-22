"""Groq chat-completion client with timeouts, retries, model fallback, usage capture and safe error messages.

The previously hard-coded `llama-3.3-70b-versatile` is no longer served by Groq (HTTP 404), which broke every
answer. Models are now configured via settings and a fallback model is tried on model-level errors.
"""
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional

from groq import APIConnectionError, APIStatusError, APITimeoutError, AsyncGroq, RateLimitError

from app.config.settings import settings

logger = logging.getLogger(__name__)

SAFE_ERROR_MESSAGE = "The language model is temporarily unavailable. Please try again in a moment."


class LLMError(Exception):
    def __init__(self, message: str = SAFE_ERROR_MESSAGE, retryable: bool = True):
        super().__init__(message)
        self.public_message = message
        self.retryable = retryable


@dataclass
class LLMUsage:
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    extra: Dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _model_params(model: str) -> Dict:
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low", "include_reasoning": False}
    if model.startswith("qwen/"):
        return {"reasoning_format": "hidden"}
    return {}


class GroqClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self.client = AsyncGroq(api_key=self.api_key, timeout=settings.LLM_TIMEOUT_SECONDS,
                                max_retries=settings.LLM_MAX_RETRIES) if self.api_key else None
        if not self.client:
            logger.warning("GROQ_API_KEY is not configured; LLM calls will fail with a clear error.")

    @property
    def available(self) -> bool:
        return self.client is not None

    def _models(self, model: Optional[str]) -> List[str]:
        primary = model or settings.LLM_MODEL
        fallback = settings.LLM_FALLBACK_MODEL
        return [primary] + ([fallback] if fallback and fallback != primary else [])

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        usage: Optional[LLMUsage] = None,
    ) -> AsyncGenerator[str, None]:
        """Yields content tokens. Raises LLMError (with a user-safe message) on failure before any token."""
        if not self.client:
            raise LLMError("The AI model is not configured on this server (missing GROQ_API_KEY).", retryable=False)
        last_exc: Optional[Exception] = None
        for m in self._models(model):
            emitted = False
            try:
                stream = await self.client.chat.completions.create(
                    model=m, messages=messages, stream=True,
                    temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
                    max_tokens=max_tokens or settings.LLM_MAX_TOKENS, **_model_params(m),
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        emitted = True
                        yield chunk.choices[0].delta.content
                    x = getattr(chunk, "x_groq", None)
                    u = getattr(x, "usage", None) if x is not None else getattr(chunk, "usage", None)
                    if u is not None and usage is not None:
                        usage.model = m
                        usage.prompt_tokens = int(getattr(u, "prompt_tokens", 0) or 0)
                        usage.completion_tokens = int(getattr(u, "completion_tokens", 0) or 0)
                if usage is not None and not usage.model:
                    usage.model = m
                return
            except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as e:
                last_exc = e
                logger.error("LLM call failed (model=%s, %s, status=%s)", m, type(e).__name__, getattr(e, "status_code", None))
                if emitted:
                    raise LLMError("The answer was interrupted. Please retry.") from e
                # Not yet streamed anything: try the fallback model (limits and availability are per model).
                continue
        if isinstance(last_exc, RateLimitError):
            raise LLMError("The AI service is rate-limited right now. Please retry shortly.") from last_exc
        raise LLMError() from last_exc

    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, max_tokens: int = 256,
        temperature: float = 0.0, usage: Optional[LLMUsage] = None,
    ) -> str:
        parts = []
        async for tok in self.stream_chat_completion(messages, model=model, temperature=temperature,
                                                     max_tokens=max_tokens, usage=usage):
            parts.append(tok)
        return "".join(parts).strip()


groq_client = GroqClient()
