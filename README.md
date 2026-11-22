# Vellum RAG

Vellum RAG is a document question-answering platform. You upload PDFs, Word files, text, Markdown or CSV, ask questions, and get answers **grounded only in your documents**, with numbered citations. Every user's documents, vectors and chats are isolated from everyone else's.

| Report | Contents |
|---|---|
| [PROJECT_AUDIT.md](PROJECT_AUDIT.md) | Initial audit: architecture and findings |
| [SECURITY_AUDIT.md](SECURITY_AUDIT.md) | Security findings, fixes and test evidence. **Read §0 if you run a live deployment** |
| [RAG_EVALUATION_REPORT.md](RAG_EVALUATION_REPORT.md) | Retrieval benchmark and Ragas / DeepEval / TruLens / Evidently / Phoenix results |
| [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) | Measured latency, throughput, before/after |
| [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md) | What was verified and how to deploy |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | **Overall status and the manual actions still required** |
| [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md) | Done and pending items, how to resume |

---

## Architecture

```
React SPA (Vite, TS) ──► nginx gateway ──► FastAPI (async, gunicorn/uvicorn)
   HttpOnly cookie session + CSRF           │
                                            ├─ Auth: Argon2id, JWT (PyJWT) bound to server-side sessions, TOTP MFA
                                            ├─ Ingestion: validate → parse (PDF/DOCX/TXT/MD/CSV) → section-aware chunks
                                            │             → MiniLM embeddings (384-d) → PostgreSQL + pgvector
                                            ├─ RAG: reformulate → hybrid retrieval (vector + full-text, RRF; owner-filtered)
                                            │       → cross-encoder rerank + relevance threshold → context builder
                                            │       → Groq LLM (fallback model) → citation validation → SSE stream
                                            ├─ Storage: private Supabase bucket or local volume
                                            ├─ Redis (rate limits)       └─ OpenTelemetry → Arize Phoenix
```

**Request flow.** Question → validation → standalone query (with chat history) → query embedding → authorised retrieval (only the caller's indexed chunks) → rerank and threshold → **if nothing is relevant, return "I couldn't find information…" without calling the LLM** → numbered `<source>` blocks (treated as untrusted data) → LLM → citations checked → answer + sources streamed.

### Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async) + asyncpg, Pydantic 2 |
| Database | PostgreSQL 16 + pgvector (exact per-tenant search; HNSW optional) + full-text GIN index |
| AI | sentence-transformers `all-MiniLM-L6-v2` (embeddings), `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker), Groq `openai/gpt-oss-120b` with `qwen/qwen3.8-27b` fallback |
| Frontend | React 18, TypeScript, Vite 8, Tailwind, react-router 7, react-markdown |
| Security | Argon2id, PyJWT, pyotp, CSRF, CSP/HSTS, rate limiting, Postgres RLS (optional) |
| Observability | Structured redacted logs, OpenTelemetry/OpenInference → Arize Phoenix, Evidently reports |
| Evaluation | Ragas, DeepEval, TruLens, Evidently, Arize Phoenix |

---

## Running locally (no Docker needed)

Prerequisites: Python 3.12 (`uv` recommended), Node 20+, a Groq API key.

```powershell
python -m pip install uv
python -m uv venv .venv --python 3.12
python -m uv pip install --python .venv\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cpu
python -m uv pip install --python .venv\Scripts\python.exe -r backend\requirements-dev.txt
```

Put only `GROQ_API_KEY=...` in `.env`. The dev scripts never read the database or Supabase settings from it.

```powershell
.venv\Scripts\python.exe scripts\local_postgres.py
```

That starts an embedded PostgreSQL 16 + pgvector. Then start the backend on http://127.0.0.1:8000:

```powershell
.venv\Scripts\python.exe scripts\dev_server.py
```

And the frontend on http://localhost:5173 (it proxies `/api` to :8000):

```powershell
npm --prefix frontend install; npm --prefix frontend run dev
```

With Docker, see [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md):

```powershell
docker compose up -d --build
```

### Environment

Every variable is documented in [.env.example](.env.example). The key ones:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `production` enforces secure settings and refuses to start with insecure ones |
| `JWT_SECRET_KEY` | **Required in production.** 64 random hex chars |
| `DATABASE_URL` | `postgresql+asyncpg://…` |
| `GROQ_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODEL` | LLM provider |
| `CORS_ORIGINS`, `COOKIE_SECURE`, `COOKIE_SAMESITE` | Browser session settings |
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_STORAGE_BUCKET` | Private storage (optional; local volume otherwise) |
| `RERANKER_ENABLED`, `RERANK_TOP_N`, `RERANK_MIN_SCORE`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `VECTOR_SEARCH` | Retrieval tuning (defaults chosen by benchmark) |
| `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `TRACE_INCLUDE_CONTENT` | Phoenix tracing |
| `ENABLE_RLS` | Database row-level security (after applying `backend/app/database/rls.sql`) |

---

## API

Interactive docs are available at `/docs` outside production. All routes are under `/api`.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | – | Create an account (password ≥ 10 chars). 5/h per IP |
| POST | `/auth/login` | – | Sets HttpOnly session cookies and returns `csrf_token` (and `access_token` for API clients). If MFA is on, returns `{mfa_required, mfa_token}` |
| POST | `/auth/login/mfa` | mfa_token | Second step with TOTP or recovery code |
| POST | `/auth/guest` | – | Isolated temporary workspace (deleted after 24 h) |
| POST | `/auth/refresh` | refresh cookie | Rotates the refresh token |
| GET | `/auth/session` | ✓ | Current user + CSRF token |
| POST | `/auth/logout` | ✓ | Revokes the session server-side |
| GET/PUT | `/auth/profile` | ✓ | View or update name |
| POST | `/auth/password` | ✓ | Change password (needs the current one; signs out other sessions) |
| POST | `/auth/mfa/setup`, `/auth/mfa/enable`, `/auth/mfa/disable` | ✓ | TOTP enrolment and removal |
| DELETE | `/auth/account` | ✓ | Delete the account and all its data |
| POST | `/upload` | ✓ | Multipart `file` (pdf, docx, txt, md, csv; ≤ 20 MB). Indexed in the background |
| GET | `/documents`, `/document/{id}` | ✓ | Own documents (admins: all metadata) |
| DELETE | `/document/{id}` | ✓ | Deletes the file, chunks and vectors |
| POST | `/query` | ✓ | SSE stream (below) |
| GET/DELETE | `/history`, `/history/{session_id}` | ✓ | Conversations |
| POST | `/build-index` | admin | Re-parse and re-embed everything |
| GET | `/stats`, `/logs` | admin | Aggregate metrics, redacted logs |
| GET | `/health`, `/health/live` | – | Readiness (DB + vectors; 503 if down) and liveness |

Cookie-authenticated `POST`/`PUT`/`DELETE` requests must send `X-CSRF-Token`. API clients can use `Authorization: Bearer <access_token>` instead and don't need CSRF.

**`POST /api/query`** takes `{"message": "...", "session_id": null, "search_mode": "hybrid"|"semantic"|"mmr", "k": 5, "document_ids": null}` and streams these SSE events:

| Event | Payload |
|---|---|
| `session` | `{session_id}` |
| `sources` | `[{ref, document_id, filename, page_number, section, similarity_score, text_content}]` |
| *(data)* | `{content}` tokens |
| `meta` | timings, token usage, citation validation |
| `error` | `{detail}` if the LLM fails mid-stream |
| `close` | `"[DONE]"` |

---

## RAG pipeline details

- **Parsing:** PDF (running headers/footers stripped, encrypted and corrupt files rejected), DOCX (headings + tables), TXT/MD (encoding detection), CSV (rows as `column: value` records). Text is normalised.
- **Chunking:** recursive paragraph → line → sentence → word splitting, **1000 chars with 150 overlap**, chosen by measurement over 500/1000/1500. Markdown section titles are tracked and stored per chunk.
- **Dedup:** SHA-256 per user; re-uploading the same file returns 409.
- **Retrieval:** vector search (exact within the user's rows) and Postgres full-text search, fused with Reciprocal Rank Fusion. The top 10 go to a cross-encoder. Chunks below `-5.0`, or more than `7.0` below the best chunk, are dropped. MMR mode diversifies.
- **Context:** near-duplicate removal, a 3,000-token budget, numbered `<source id=n file=… page=…>` blocks. Delimiters inside documents are escaped, and instruction-like chunks are flagged.
- **Generation:** a rules-only system prompt. Sources are declared untrusted. The model answers only from sources, cites `[n]`, and uses a fixed refusal sentence when the answer isn't there. Invalid citations are stripped and reported in `meta`.

## Evaluation

```powershell
.venv-eval\Scripts\python.exe evaluation\run_all_evaluations.py --parallel
```

Setup is in [evaluation/requirements-eval.txt](evaluation/requirements-eval.txt). The run covers Ragas, DeepEval, TruLens, Evidently and Phoenix; use `--ids` for a subset. A retrieval-only benchmark needs no LLM:

```powershell
.venv\Scripts\python.exe evaluation\retrieval_benchmark.py --db-url <eval db>
```

Results, the dataset and their limitations are in [RAG_EVALUATION_REPORT.md](RAG_EVALUATION_REPORT.md).

## Testing

```powershell
.venv\Scripts\python.exe -m pytest
```

That runs 88 offline tests (unit, API, security, RLS, reliability) against an isolated local DB with a fake LLM. Live tests against Groq (grounding, refusal, prompt injection, DeepEval assertion):

```powershell
.venv\Scripts\python.exe -m pytest -m live tests\live
```

Security scans (Bandit, Semgrep, pip-audit, detect-secrets, npm audit):

```powershell
.venv\Scripts\python.exe scripts\security_scan.py
```

Dynamic probe of a running local server:

```powershell
.venv\Scripts\python.exe scripts\dast_probe.py
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Invalid configuration: JWT_SECRET_KEY…" at startup | Production needs a private secret: `python -c "import secrets;print(secrets.token_hex(32))"` |
| Answers say the model is unavailable or rate-limited | Groq quota (free tier: 200K tokens/day per model). The fallback model is tried automatically; upgrade the Groq tier for production |
| Logged out on every request in a cross-site setup | Use `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` + exact `CORS_ORIGINS`, or serve the API from the same origin |
| Document stuck in `failed` | Hover the status to see `error_message` (scanned PDF without text, encrypted, corrupt) |
| First request slow after a deploy | Models warm in the background for about 20 s after startup |
| `greenlet` import error | Install `sqlalchemy[asyncio]` (already in requirements) |
