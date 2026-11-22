# REST API

The full endpoint table, request bodies and SSE event format are in the [README](../README.md#api). Interactive OpenAPI docs are served at `/docs` when `ENVIRONMENT` is not `production`.

## Authentication

**Browsers.**
- `POST /api/auth/login` (or `/api/auth/guest`) sets HttpOnly cookies `vellum_access` (30 min, path `/api`) and `vellum_refresh` (7 days, path `/api/auth`), and returns a `csrf_token`.
- Send it as `X-CSRF-Token` on every POST/PUT/DELETE.
- Call `POST /api/auth/refresh` on 401.

**API clients.** Use the `access_token` from the login response as `Authorization: Bearer <token>`. CSRF does not apply to Bearer requests.

```bash
curl -s -X POST https://host/api/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"user@example.com","password":"<password>"}'
curl -N https://host/api/query -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"message":"What is the refund policy?","search_mode":"hybrid","k":5}'
```

If MFA is enabled, login returns `{"mfa_required": true, "mfa_token": "..."}`. Complete it with:

```
POST /api/auth/login/mfa  {"mfa_token": "...", "code": "123456"}
```

## Gloss

After each streamed answer, a `gloss` event carries a deterministic, lexical check of every claim against the passage its `[n]` citation points to (`app/retrieval/gloss.py`). `GET /api/history/{id}` recomputes it for stored answers. It flags unsupported figures and citations to passages that were never retrieved. It cannot judge paraphrase.

## Errors

- JSON `{"detail": "..."}` with the usual status codes: 400, 401, 403, 404 (also used for resources you don't own), 409 (duplicate upload), 413, 415, 422, 429 (with `Retry-After`) and 503 (health).
- Server errors return a generic message; details go to the server log only.
