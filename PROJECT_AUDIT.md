# Project Audit: Vellum RAG

**Audit date:** 2026-11-22
**Scope:** the full repository at commit `20c2aef` plus the uncommitted working-tree changes (FAISS removal, doc edits).
**Method:** I read every backend module, the frontend services, hooks and contexts, the Docker, Compose and nginx files, the existing tests and the docs, and probed the configured LLM provider at runtime.

---

## 1. Existing architecture

```
React SPA (Vite/TS) ──► nginx ──► FastAPI (async) ──► PostgreSQL + pgvector (Supabase in prod)
     │                               │  ├─ SentenceTransformers all-MiniLM-L6-v2 (384-d, local CPU)
     │ (stream bypasses proxy,       │  ├─ Groq chat completions (streaming SSE)
     │  calls Render URL directly)   │  ├─ Supabase Storage (public bucket) or local uploads/
     └───────────────────────────────┘  └─ Redis (rate limiter, in-memory fallback)
```

| Layer | Files |
|---|---|
| API | `backend/app/api/{auth,documents,chat,admin,schemas}.py` |
| Auth | `backend/app/auth/{jwt,dependencies}.py` (python-jose HS256, bcrypt) |
| Ingestion | `backend/app/ingestion/{parser,chunker}.py`, `services/document_service.py` |
| Embeddings | `backend/app/embeddings/embedder.py` |
| Retrieval | `backend/app/retrieval/retriever.py` (semantic / MMR / ILIKE hybrid) |
| Generation | `backend/app/llm/groq_client.py`, `prompts/rag_prompts.py`, `services/chat_service.py` |
| Data | `backend/app/models/*.py`. Schema is created with `create_all` at startup, with no migrations. |
| Deploy | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `nginx/`. The frontend references a Render backend URL. |

The working tree has already removed the FAISS store (`vectorstore/`), and no remaining code imports it.

---

## 2. Findings

Severity scale: **Critical**: exploitable now, or the core feature is broken. **High**: serious risk or defect. **Medium**: quality or robustness. **Low**: hygiene.

### 2.1 Runtime / functional

| # | Severity | Finding | Files | Fix |
|---|---|---|---|---|
| F1 | **Critical** | **LLM generation is broken.** The hard-coded model `llama-3.3-70b-versatile` returns HTTP 404 from Groq because it is no longer offered. Every chat answer becomes `*(Error communicating with Groq API: …)*`. Query reformulation also fails silently. | `llm/groq_client.py` | Make the model configurable and default to an available model (`openai/gpt-oss-120b`) with a fallback. Add retries, timeouts and generic error messages. |
| F2 | High | `HTTPException` is raised *inside* the SSE generator for an invalid `session_id`. By then the 200 response has started, so the client gets a broken stream instead of a 404. | `services/chat_service.py` | Validate before the stream starts. |
| F3 | High | CPU-bound embedding (`model.encode`) and parsing run directly on the asyncio event loop. While they run, all concurrent requests stall. | `embeddings/embedder.py`, `retrieval/retriever.py`, `services/document_service.py` | Offload to a threadpool. |
| F4 | High | No vector index exists, so every query is a sequential scan over all chunks. | `models/document.py` | Add an HNSW `vector_cosine_ops` index. |
| F5 | High | No relevance threshold. The top-k chunks always go to the LLM even when they are unrelated, and the prompt then allows a "general knowledge" fallback. This is the main source of hallucination. | `retrieval/retriever.py`, `prompts/rag_prompts.py` | Add a similarity threshold. When nothing passes, return a grounded refusal without calling the LLM. |
| F6 | Medium | The hybrid keyword leg takes `ILIKE '%term%'` OR-matches with `LIMIT k*2` in arbitrary (unranked) order, so the "keyword" candidates are effectively random among matches. | `retrieval/retriever.py` | Use Postgres full-text search (`tsvector` + `ts_rank_cd`) fused with RRF. |
| F7 | Medium | The chunker runs `text.split()` and collapses all newlines, paragraphs and headings. `parse_txt` pre-splits text into 2000-char fake "pages" mid-word *before* chunking. Overlap is estimated from an assumed 6-char word length. | `ingestion/chunker.py`, `ingestion/parser.py` | Use a recursive paragraph→sentence→word splitter with real char overlap and heading/section metadata. |
| F8 | Medium | DOCX tables are ignored. CSV is not supported. The encoding fallback list includes `latin-1` *before* `cp1252`, so `cp1252` is unreachable. | `ingestion/parser.py` | Parse DOCX tables, add CSV, fix the decoding order and normalise text. |
| F9 | Medium | No duplicate detection. The same file can be indexed many times, which duplicates retrieval results. | `services/document_service.py` | Store a per-user SHA-256 content hash and reject duplicates. |
| F10 | Medium | N+1 query: one `SELECT documents` per retrieved chunk. | `services/chat_service.py` | Batch the lookup. |
| F11 | Medium | Embeddings are not L2-normalised, the dimension is hard-coded rather than checked against the model, and query embeddings are recomputed for each retrieval call (hybrid computes them twice). | `embeddings/embedder.py` | Normalise, check the dimension at startup, cache query embeddings. |
| F12 | Medium | Citations are only formatted as `[filename, Page X]`. Nothing checks them after generation, and sources include chunks the model never used. | `prompts/`, `services/chat_service.py` | Use numbered `[n]` citations mapped to sources, and validate them after generation. |
| F13 | Medium | Upload has no size limit: `MAX_UPLOAD_SIZE_MB` is defined but never enforced, and the entire file is read into memory. | `services/document_service.py` | Do a capped streaming read and return 413. |
| F14 | Low | `AdminService.get_system_stats` returns hard-coded "mock" API usage (`auth_requests: 140`). The logs endpoint falls back to fabricated log lines. | `services/admin_service.py` | Report real numbers, or say clearly that the data is unavailable. |
| F15 | Low | `datetime.utcnow()` is deprecated. `@app.on_event` is deprecated. | many | Use the lifespan handler and timezone-aware datetimes. |
| F16 | Low | `tests/test_database_retrieval.py` writes to whatever `DATABASE_URL` points to. In this checkout that is the **production Supabase database**. | `tests/` | Use an isolated test database fixture. |
| F17 | Low | The PDF/docs make claims the code does not implement: Content-Length 413 middleware, `<context>` prompt-injection delimiters, Alembic migrations, applied rate limiting, `pool_size=20`. | docs | Implement the features or correct the docs. |

### 2.2 Security (detail in `SECURITY_AUDIT.md`)

| # | Severity | Finding | Files |
|---|---|---|---|
| S1 | **Critical** | **Shared anonymous "guest" account.** Requests without a token are silently authenticated as `guest@vellum.ai`, so every anonymous visitor shares one account. They can all see, query and delete each other's uploaded documents and chat history. The guest password `guest123` is also seeded. | `auth/dependencies.py`, `main.py` |
| S2 | **Critical** | **Publicly known JWT secret.** The default `JWT_SECRET_KEY` is committed in `settings.py`, `docker-compose.yml` and `.env.example`, and the local `.env` uses that same value. Anyone who reads the repo can forge a token for any email, including the admin. | `config/settings.py`, `docker-compose.yml`, `.env.example` |
| S3 | **Critical** | **Default admin credentials.** `admin@vellum.ai` / `admin123` is seeded on startup whenever `ADMIN_PASSWORD` is unset (it is unset in `.env`). | `config/settings.py`, `main.py` |
| S4 | High | **Uploaded documents are publicly readable.** Supabase uploads are stored and parsed through `get_public_url`, which requires a public bucket. Anyone with the URL can read private documents, and the object path contains only the user id and a 32-bit random number. | `services/document_service.py`, `ingestion/parser.py` |
| S5 | High | The parser fetches any `http(s)` URL stored in `documents.filepath` with redirects allowed. This is an SSRF primitive if that column is ever attacker-influenced. | `ingestion/parser.py` |
| S6 | High | Rate limiter exists but **is not applied to any route** (login brute force, registration, uploads, LLM cost). Its key also uses `request.client.host`, which behind a proxy is the proxy's IP. | `middleware/rate_limiter.py` |
| S7 | High | The first registered user becomes admin (race on a fresh database). | `services/auth_service.py` |
| S8 | High | No prompt-injection defences. Retrieved text is placed *inside the system prompt*, nothing marks it as untrusted, and the prompt invites general-knowledge answers. | `prompts/rag_prompts.py`, `services/chat_service.py` |
| S9 | High | JWT is stored in `localStorage` (exfiltrated by any XSS). The token lasts 24 h, has no `iss`/`aud`/`jti`, cannot be revoked, and logout is client-side only. `python-jose` has known CVEs (CVE-2024-33663/33664). | `auth/jwt.py`, `frontend/src/context/AuthContext.tsx`, `services/api.ts` |
| S10 | Medium | CORS `allow_origins=["*"]` with all methods and headers. | `main.py` |
| S11 | Medium | Upload checks the extension only: no MIME type, magic bytes, zip-bomb limits or filename sanitisation. The user-supplied filename is concatenated into storage paths. | `services/document_service.py` |
| S12 | Medium | Raw exception text is returned to clients (Supabase errors, Groq errors in the stream). | `document_service.py`, `groq_client.py` |
| S13 | Medium | Password change does not require the current password. There is no length policy (min 6), no MFA, and bcrypt where Argon2id is preferred. | `api/auth.py`, `api/schemas.py` |
| S14 | Medium | No security headers (CSP, HSTS, nosniff, frame-ancestors) on nginx or the API. `/docs` is exposed in production. `DEBUG=True` by default. | `nginx/nginx.conf`, `main.py` |
| S15 | Medium | The container runs as root. Postgres and Redis ports are published to the host. A hard-coded Postgres password is in Compose. | `backend/Dockerfile`, `docker-compose.yml` |
| S16 | Low | No database row-level security. Isolation relies solely on application `WHERE` clauses. | DB |
| S17 | Low | No dependency lockfile: all `>=` ranges, so builds are not reproducible. | `backend/requirements.txt` |
| S18 | Low | Logs (`app.log`) are written unrotated with no redaction, and are served by the admin `/logs` endpoint. | `main.py`, `admin_service.py` |

### 2.3 Frontend

| # | Severity | Finding | Files |
|---|---|---|---|
| U1 | High | When the profile request fails, the client invents a fake guest user (`id: 1`) and shows the UI as if logged in. | `context/AuthContext.tsx` |
| U2 | Medium | The streaming error message shows only `HTTP status N`, and the server's `detail` is dropped. | `hooks/useChat.ts` |
| U3 | Medium | After the first message of a new chat, the post-stream refresh is skipped because `activeSessionId` in the closure is stale. | `hooks/useChat.ts` |
| U4 | Low | The backend URL `https://rag-backend-8pv0.onrender.com` is hard-coded rather than configured. | `hooks/useChat.ts` |
| — | OK | Markdown rendering uses `react-markdown` without `rehype-raw`, so raw HTML is not rendered and `javascript:` URLs are stripped by the default URL transform. There is no `dangerouslySetInnerHTML`. | `components/ChatInterface.tsx` |

---

## 3. Implementation priorities

1. **P0:** F1 (LLM 404), S1 (shared guest), S2/S3 (forgeable tokens and default admin), S4 (public documents). Users are exposed or the core feature is down.
2. **P1:** S6 rate limiting, S8 prompt injection, F5 grounding/threshold, F2/F3 runtime correctness, S9 cookie sessions, S11/F13 upload validation, S5 SSRF.
3. **P2:** retrieval quality (F4, F6, F7, F11, F12), ingestion robustness (F8, F9), headers/CORS/logging, MFA, RLS.
4. **P3:** evaluation frameworks, the test suite, performance measurement, docs.

## 4. Environment constraints found during the audit

- Docker Desktop is installed but its engine would not start in this session, so local Postgres/pgvector testing uses `pgserver` (an embedded PostgreSQL 16 + pgvector).
- The machine has Python 3.14 only, and several evaluation libraries do not support it. A Python 3.12 virtualenv (`.venv`) was created.
- Groq limits for the available models are **8,000 tokens/min and 1,000 requests/day per model**. These limits bound the size of LLM-judged evaluations.
- `.env` points at the production Supabase database. No tests or evaluations in this work are run against it.
