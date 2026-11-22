"""OpenTelemetry tracing with OpenInference semantic conventions (renders natively in Arize Phoenix).

Enabled with OTEL_ENABLED=true; spans are exported over OTLP/HTTP to OTEL_EXPORTER_OTLP_ENDPOINT
(Phoenix: http://<host>:6006/v1/traces). When disabled, the no-op tracer is used and the overhead is negligible.

Privacy: prompts, document text, questions and answers are only attached when TRACE_INCLUDE_CONTENT=true
(intended for local evaluation runs). All string attributes are passed through the log redactor.
"""
import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from opentelemetry import trace

from app.config.logging_config import redact
from app.config.settings import settings

logger = logging.getLogger(__name__)
_configured = False
TRACER_NAME = "vellum.rag"

# OpenInference attribute names (https://github.com/Arize-ai/openinference/tree/main/spec)
KIND = "openinference.span.kind"
INPUT = "input.value"
OUTPUT = "output.value"


def setup_tracing(endpoint: Optional[str] = None, service_name: Optional[str] = None, force: bool = False) -> bool:
    global _configured
    if _configured or not (settings.OTEL_ENABLED or force):
        return _configured
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        resource = Resource.create({"service.name": service_name or settings.OTEL_SERVICE_NAME,
                                    "openinference.project.name": service_name or settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint or settings.OTEL_EXPORTER_OTLP_ENDPOINT)))
        trace.set_tracer_provider(provider)
        _configured = True
        logger.info("Tracing enabled (OTLP -> %s)", endpoint or settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    except Exception as e:  # tracing must never break the app
        logger.warning("Tracing setup failed: %s", type(e).__name__)
    return _configured


def shutdown_tracing() -> None:
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()


def tracer():
    return trace.get_tracer(TRACER_NAME)


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)[:8000]
    if isinstance(value, (dict, list)):
        return redact(json.dumps(value, default=str))[:8000]
    return value


def content_allowed() -> bool:
    return settings.TRACE_INCLUDE_CONTENT


@contextmanager
def span(name: str, kind: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[trace.Span]:
    with tracer().start_as_current_span(name) as s:
        s.set_attribute(KIND, kind)
        for k, v in (attributes or {}).items():
            if v is not None:
                s.set_attribute(k, _clean(v))
        try:
            yield s
        except Exception as e:
            s.record_exception(e)
            s.set_status(trace.Status(trace.StatusCode.ERROR, type(e).__name__))
            raise


def set_attrs(s, attributes: Dict[str, Any], content: bool = False) -> None:
    """Set attributes; `content=True` marks values that are only exported when TRACE_INCLUDE_CONTENT is on."""
    if content and not content_allowed():
        return
    for k, v in attributes.items():
        if v is not None:
            s.set_attribute(k, _clean(v))
