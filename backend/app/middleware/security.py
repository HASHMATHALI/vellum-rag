"""Security headers and request-id middleware (pure ASGI so SSE streaming is not buffered)."""
import time
import uuid
import logging

from app.config.settings import settings

logger = logging.getLogger("app.access")

# The API only returns JSON / SSE, so the CSP can be maximally strict. Swagger UI (/docs) needs its CDN assets.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid.uuid4())
        path = scope.get("path", "")
        start = time.perf_counter()
        status_holder = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}

                def add(name: str, value: str):
                    if name.encode() not in existing:
                        headers.append((name.encode(), value.encode()))

                add("x-request-id", request_id)
                add("x-content-type-options", "nosniff")
                add("x-frame-options", "DENY")
                add("referrer-policy", "no-referrer")
                add("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
                add("cross-origin-opener-policy", "same-origin")
                add("content-security-policy", DOCS_CSP if path in ("/docs", "/redoc") else API_CSP)
                if settings.is_production:
                    add("strict-transport-security", "max-age=63072000; includeSubDomains")
                if path.startswith("/api/auth") or path.startswith("/api/history"):
                    add("cache-control", "no-store")
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if not path.startswith("/api/health"):
                logger.info("%s %s %s %.0fms rid=%s", scope.get("method"), path, status_holder.get("status"),
                            (time.perf_counter() - start) * 1000, request_id)
