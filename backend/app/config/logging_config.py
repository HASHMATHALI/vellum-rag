"""Structured logging with secret redaction.

Every record passes through RedactingFilter, which masks bearer tokens, JWTs, API keys, passwords and
connection-string credentials before anything reaches a handler (console, rotating file, admin /logs).
"""
import json
import logging
import re
from logging.handlers import RotatingFileHandler

from app.config.settings import settings

_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)((?:password|passwd|secret|api[_-]?key|token|otp|code)\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1[REDACTED]"),
    (re.compile(r"([a-z][a-z0-9+.-]*://[^:/\s@]+:)[^@\s/]+@"), r"\1[REDACTED]@"),
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = ()
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "user_id", "path", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_text:
            payload["exc"] = record.exc_text
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_vellum_configured", False):
        return
    root.setLevel(settings.LOG_LEVEL.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = JsonFormatter() if settings.LOG_JSON else logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handlers = [logging.StreamHandler()]
    if settings.LOG_FILE:
        handlers.append(RotatingFileHandler(settings.LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    # Third-party loggers that may echo request bodies or URLs at DEBUG.
    for noisy in ("httpx", "httpcore", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._vellum_configured = True  # type: ignore[attr-defined]
