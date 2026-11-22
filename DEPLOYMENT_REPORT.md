# Deployment Report: Vellum RAG

**Date:** 2026-11-22

## Status at a glance

| Item | Status |
|---|---|
| Production configuration prepared (Dockerfiles, Compose, nginx, `.env.example`, lock files) | **Done** |
| Production-mode run, verified locally (backend `ENVIRONMENT=production` + production frontend build) | **Done.** Checks below |
| `docker compose up` of the full stack | **Done and verified** (§3b): 5/5 containers healthy, end-to-end RAG through the gateway, DAST 25/25, persistence across restarts |
| Deployment to a cloud host (Render) | **Not performed: awaiting your approval.** Nothing was pushed or deployed |
| Live production URL verified | **No.** No deployment URL is claimed |

## 3b. Docker Compose verification (Docker Engine 29.9.3, Compose v5.7)

Run as an isolated project with its own env file, so it could never touch the production Supabase settings in `.env`:

```
docker compose -p vellum-verify --env-file .env.docker.local up -d
```

| Check | Result |
|---|---|
| Image build | ✅ backend 2.57 GB (torch CPU + baked models), frontend 74 MB, gateway 74 MB |
| Containers | ✅ postgres (healthy), redis (healthy), **backend / RAG (healthy)**, frontend, nginx: all up |
| Non-root | ✅ backend uid 10001, nginx uid 101 |
| Network exposure | ✅ only the gateway is published (`:8080`); Postgres and Redis are internal |
| Gateway | ✅ `/` and `/dashboard` 200 (SPA), `/docs` and `/openapi.json` 404, `*.map` 404, CSP + DENY framing headers |
| Startup | ✅ migrations applied, models warmed in ~15 s, JSON logs |
| RAG end-to-end via `:8080` | ✅ PDF uploaded → indexed (34 chunks). "Why did the project migrate from FAISS to pgvector?" → grounded answer with `[1][2]` citations (gpt-oss-120b). "Capital of Australia?" → refused, **no LLM call** |
| Cookies | ✅ HttpOnly |
| DAST probe through the gateway | ✅ 25/25 (`reports/security/dast_probe_docker.json`) |
| Persistence | ✅ `restart postgres backend`: vectors 36 → 36, services healthy again |

**Found and fixed during this run.** The probe's traversal check expected 404, but behind nginx `../../etc/passwd` is normalised and the SPA `index.html` is served. The body contains no file content, so this is not a vulnerability. The check now accepts the SPA fallback and still fails on any file disclosure.

**Upgrade gotcha.** An existing `rag_postgres_data` volume from the original Compose setup (user `postgres`, old password) makes the new backend fail with `password authentication failed for user "vellum"`. Postgres applies `POSTGRES_USER`/`POSTGRES_PASSWORD` only when a volume is first initialised. Your old volumes (`rag_postgres_data`, `rag_uploads_data`, `rag_vector_store_data`) were **left untouched**. To reuse them, set `POSTGRES_USER=postgres` and the old password in `.env`, or migrate the data. Otherwise start fresh with a new project name or volume.

**Minor.** With `WEB_CONCURRENCY=2`, each worker runs the idempotent migrations at startup. This is harmless (all `IF NOT EXISTS`), but a one-off migration job is cleaner at larger scale.

## 1. Existing infrastructure (inspected)

The repository and frontend code point to **Render**: the backend at `https://rag-backend-8pv0.onrender.com`, a frontend static site, and Supabase for Postgres + pgvector and Storage. There is also a single-host Docker Compose setup with nginx. I kept that architecture and did not migrate platforms.

## 2. What was prepared

| File | Production properties |
|---|---|
| `backend/Dockerfile` | python:3.12-slim. Installs the **exact lock file** (`requirements.lock`, CPU-only torch, no CUDA wheels). Embedding and reranker models baked into the image, with `HF_HUB_OFFLINE=1` so it starts offline. **Non-root user** (uid 10001). Gunicorn supervising uvicorn workers (`WEB_CONCURRENCY`), honouring `$PORT` for PaaS. `HEALTHCHECK` on `/api/health`. `ENVIRONMENT=production` and JSON logs by default |
| `frontend/Dockerfile` + `nginx-spa.conf` | node:22 build (`npm ci`, Vite 8). `.map` files deleted. **nginx-unprivileged** on :8080. Immutable caching for hashed assets, `no-cache` for `index.html`, SPA fallback |
| `nginx/` | Unprivileged gateway on :8080 serving SPA and API from one origin (first-party cookies, no CORS needed). Strict CSP, nosniff, DENY framing, Referrer-Policy, Permissions-Policy, COOP. Edge rate limits (auth 2 r/s, API 20 r/s). SSE buffering off. `/docs` blocked. `server_tokens off`. Access logs to stdout |
| `docker-compose.yml` | No secrets in the file: `${VAR:?}` makes `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` and `GROQ_API_KEY` mandatory. Postgres and Redis on an internal network only (not published). Healthchecks, `depends_on: service_healthy`, `no-new-privileges`, memory/CPU limits, restart policies, persistent volumes for DB and uploads. Optional `phoenix` service under the `observability` profile, bound to 127.0.0.1 |
| `.env.example` | Every setting documented. REQUIRED values marked, with secure defaults (`COOKIE_SECURE=true`, `TRACE_INCLUDE_CONTENT=false`) |
| `backend/app/database/rls.sql` | Optional DB-enforced tenant isolation (see SECURITY_AUDIT S16) |

**Startup safety.** With `ENVIRONMENT=production` the app **refuses to start** if `JWT_SECRET_KEY` is missing, shorter than 32 chars or a known public value, if `ADMIN_PASSWORD` is weak, or if `CORS_ORIGINS` contains `*`. Configuration errors are reported without echoing secret values. Migrations are idempotent and run at startup (adding columns and indexes to the existing Supabase schema without data loss).

## 3. Production-like verification performed (local)

Backend `ENVIRONMENT=production` with a fresh random secret on :8100, against local PostgreSQL 16 + pgvector, with the **production build** of the frontend served by `vite preview` on :4173.

| Check | Result |
|---|---|
| App starts; migrations applied; models warmed in the background | ✅ |
| Starts with empty or known-public `JWT_SECRET_KEY` | ✅ refused with a sanitised message (no secret values printed) |
| `/docs`, `/redoc`, `/openapi.json` | ✅ 404 in production |
| Security headers incl. HSTS and CSP | ✅ present |
| Production bundle contains source maps | ✅ none |
| Frontend loads; isolated guest session; no token readable from JS (`document.cookie` empty, nothing in `localStorage`) | ✅ |
| Upload → background indexing | ✅ `handbook.txt` indexed |
| Question → retrieval → LLM → cited answer in UI | ✅ "Incident reports must be filed within 24 hours using form NW-17 [1]", sources panel "1 cited of 1 retrieved" |
| LLM resilience | ✅ Primary model hit its daily limit (429), the **fallback model answered** (server log) |
| Health checks | ✅ `/api/health` 200 (DB + vector store), `/api/health/live` 200; 503 when the DB is down (tested) |
| Authentication, user isolation, rate limits, CSRF | ✅ automated tests (88) + DAST probe (25/25) against the running server |
| Vector persistence across restarts | ✅ `test_vectors_persist_across_engine_restart`; dev-server restarts kept indexed documents |
| Evaluation commands | ✅ run (see RAG_EVALUATION_REPORT.md; LLM-judged scope limited by Groq quotas) |

## 4. Deploying to Render (steps for you)

Do the **§0 actions in SECURITY_AUDIT.md first**: rotate `JWT_SECRET_KEY`, change the admin password, make the bucket private.

### Backend (Render Web Service, Docker)
- Root `backend/`, Dockerfile build. Render injects `$PORT` and the image honours it.
- Health check path `/api/health`.
- Instance size: at least 2 GB RAM (models + torch). Set `WEB_CONCURRENCY=1` on small instances.
- Environment variables:
  - `ENVIRONMENT=production`
  - `JWT_SECRET_KEY=<new 64-hex>`
  - `DATABASE_URL=postgresql+asyncpg://…supabase…` (the pooler URL works; prepared-statement caching is disabled for it automatically)
  - `GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` (server key; **private** bucket)
  - `CORS_ORIGINS=https://<your-frontend>.onrender.com`
  - `COOKIE_SECURE=true`, `TRUSTED_PROXY_HOPS=1`
  - `REDIS_URL` (Render Key Value) for shared rate limits
  - Optionally `ADMIN_EMAIL` / `ADMIN_PASSWORD` (≥12 chars, not a default)
- **Cookies across sites.** `*.onrender.com` is on the Public Suffix List, so a frontend and backend on two `onrender.com` subdomains are **cross-site**. Either:
  - (a) recommended: serve the API under the frontend's origin through a rewrite (`/api/*` → backend) and keep `COOKIE_SAMESITE=lax`; or
  - (b) call the backend directly (`VITE_API_BASE_URL=https://<backend>.onrender.com`) and set `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true`. CSRF tokens protect state-changing requests in both modes.

  The original code bypassed the rewrite for SSE because the static-site proxy buffered streams. If that is still true, use (b) or a custom domain on both services (same site, then option a works with `api.` and `app.` subdomains).

### Frontend (Render Static Site)
- Build `npm ci && npm run build`, publish `frontend/dist`.
- Rewrite `/*` → `/index.html`, plus `/api/*` for option (a).
- Build env `VITE_API_BASE_URL` for option (b).
- Add response headers matching `nginx/nginx.conf` (CSP etc.) in Render's header settings.

### Post-deploy verification
- `curl -I https://<backend>/api/health` → 200 with HSTS.
- Then run, from a machine that can reach it:
  ```
  python scripts/dast_probe.py --base https://<host>
  ```
  The probe only targets localhost by default; adjust the guard deliberately for your own host.

## 5. Single-host Docker Compose (where Docker works)

```
cp .env.example .env        # fill POSTGRES_PASSWORD, JWT_SECRET_KEY, GROQ_API_KEY
docker compose up -d --build
curl http://localhost:8080/api/health
docker compose --profile observability up -d phoenix   # optional tracing UI on 127.0.0.1:6006 (set OTEL_ENABLED=true)
```

Put TLS in front (Caddy, Traefik, a cloud LB), then set `COOKIE_SECURE=true` and enable the HSTS line in `nginx.conf`.

## 6. Remaining requirements and risks

1. Docker build and Compose run verified locally (§3b). Add the same to CI: `docker compose build`, then `pytest`, then ZAP baseline.
2. Groq free-tier quota (200K tokens/day per model) caps capacity at roughly 130 answers/day on the primary model. Use a paid tier for production.
3. CPU-bound reranking caps throughput at about 0.8–1 req/s per 4-core worker (PERFORMANCE_REPORT.md).
4. RLS (`rls.sql`) is ready but not applied to Supabase.
5. Backups: Supabase PITR or daily `pg_dump`. Uploads live in the private bucket or the `uploads_data` volume.
