"""Prompt-injection signals for retrieved/uploaded text.

Two layers:
- `heuristic_score`: fast local regex scoring, computed for every chunk at ingestion (stored in injection_score).
- `prompt_guard_scores`: optional Llama Prompt Guard 2 classifier on Groq for retrieved chunks
  (PROMPT_GUARD_ENABLED). Results are cached on the chunk row.

Flagged chunks are NOT silently dropped (a document *about* prompt injection is legitimate content). They are
marked in the context so the model treats them with extra caution; the structural defences in the prompt are the
primary control. Neither layer is a guarantee.
"""
import logging
import re
from typing import List

from app.config.settings import settings

logger = logging.getLogger(__name__)

_PATTERNS = [
    (r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|system)\b.{0,30}\b(instruction|prompt|rule|direction)s?", 0.6),
    (r"\byou are now\b|\bact as\b.{0,30}\b(admin|developer|dan|jailbreak)", 0.4),
    (r"\b(reveal|print|show|output|leak)\b.{0,40}\b(system prompt|instructions|api key|secret|password|token)s?\b", 0.5),
    (r"<\|?(im_start|im_end|system|endoftext)\|?>|\[/?INST\]|<<SYS>>", 0.6),
    (r"^\s*(system|assistant)\s*:", 0.3),
    (r"\b(send|post|exfiltrate|upload)\b.{0,40}\b(https?://|data to)", 0.4),
    (r"\bdo not (tell|inform|mention)\b.{0,30}\buser\b", 0.3),
]
_COMPILED = [(re.compile(p, re.IGNORECASE | re.MULTILINE), w) for p, w in _PATTERNS]


def heuristic_score(text: str) -> float:
    score = 0.0
    for rx, w in _COMPILED:
        if rx.search(text):
            score += w
    return min(1.0, score)


async def prompt_guard_scores(texts: List[str]) -> List[float]:
    """Llama Prompt Guard 2 via Groq: returns the probability that each text is a jailbreak/injection.
    Returns heuristic scores if the classifier is disabled or unavailable."""
    if not settings.PROMPT_GUARD_ENABLED or not settings.GROQ_API_KEY:
        return [heuristic_score(t) for t in texts]
    from app.llm.groq_client import groq_client
    out = []
    for t in texts:
        try:
            resp = await groq_client.client.chat.completions.create(
                model=settings.PROMPT_GUARD_MODEL, messages=[{"role": "user", "content": t[:2000]}], max_tokens=8)
            out.append(float((resp.choices[0].message.content or "0").strip()))
        except Exception as e:
            logger.warning("Prompt Guard unavailable (%s); using heuristic score.", type(e).__name__)
            out.append(heuristic_score(t))
    return out
