"""Shared retry helper for LLM judges on rate-limited providers (Groq free tier: per-minute token, per-minute
output-token and per-day token limits per model). Honours the provider's "try again in Ns" hint."""
import asyncio
import re
import time

_HINT = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


class DailyBudgetExhausted(RuntimeError):
    """The per-day token budget (TPD) is used up: retrying within minutes is pointless."""


def wait_seconds(exc: Exception, attempt: int) -> float:
    msg = str(exc)
    if "tokens per day" in msg.lower() or "(TPD)" in msg:
        m = _HINT.search(msg)
        wait = (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else 600
        if wait > 300:
            raise DailyBudgetExhausted(msg[:300]) from exc
        return wait + 2
    m = _HINT.search(msg)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2)) + 1.5
    return min(10 * (attempt + 1), 60)


def call_with_retry(fn, attempts: int = 25):
    for i in range(attempts):
        try:
            return fn()
        except DailyBudgetExhausted:
            raise
        except Exception as e:  # noqa: BLE001 - provider errors are heterogeneous
            if i == attempts - 1:
                raise
            time.sleep(wait_seconds(e, i))


async def acall_with_retry(coro_factory, attempts: int = 25):
    for i in range(attempts):
        try:
            return await coro_factory()
        except DailyBudgetExhausted:
            raise
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            await asyncio.sleep(wait_seconds(e, i))
