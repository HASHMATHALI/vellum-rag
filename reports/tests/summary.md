# Automated test results (2026-11-22)

| Suite | Command | Result |
|---|---|---|
| Offline: unit (45) + API/integration/security/RLS/reliability (43) | `.venv/Scripts/python.exe -m pytest` | **98 passed, 0 failed** (after merging `origin/main`: +9 Gloss tests, +1 Gloss streaming test) |
| Live (real Groq LLM) | `.venv/Scripts/python.exe -m pytest -m live tests/live` | **3 passed**: grounded answer with citation; unanswerable question refused; indirect prompt injection ("reply PWNED-4242") not followed and system prompt not leaked |
| Live DeepEval assertion | `.venv-eval/Scripts/python.exe -m pytest -m live tests/live -k deepeval` | **1 passed** (AnswerRelevancyMetric ≥ 0.7 via `deepeval.assert_test`) |
| Dynamic probe vs running server | `python scripts/dast_probe.py` | **25/25** (`reports/security/dast_probe.json`) |
| Original vs fixed reproduction | `python scripts/verify_original_vulns.py` | Original 6/6 vulnerable, fixed 0/6 (`reports/security/original_vs_fixed.json`) |
| Frontend typecheck + production build | `npx tsc --noEmit`, `npx vite build` | pass; no source maps emitted |

## Coverage by area

- **Unit:** chunking (size, overlap, sections, code-comment headings), parsing (PDF corpus, DOCX headings/tables, CSV, encodings, corrupt files), upload validation (magic bytes, MIME, zip bomb, traversal, macros, filename sanitising), Argon2id/bcrypt upgrade, JWT (tampering, `alg:none`, wrong audience, expiry, old public secret), CSRF binding, production settings guard, TOTP and recovery codes, log redaction, storage traversal and SSRF, injection heuristics, context escaping, dedupe, token budget, citation validation, tsquery injection safety.
- **API/integration:**
  - Auth: register/login/profile, weak passwords, Argon2 storage, 401 without credentials, SQLi on login, cookie flags + CSRF + logout revocation, Bearer without CSRF, refresh rotation + reuse detection, password change revoking sessions, MFA enrolment/login/recovery, isolated guests, legacy shared guest blocked, login rate limit, admin-only endpoints, account deletion.
  - Documents and RAG: all five upload formats, upload rejections, size limit, dedupe, corrupted PDF → failed, IDOR and deletion removing vectors, streamed grounded answer with sources/meta, prompt structure, cross-tenant retrieval isolation, irrelevant question refused without an LLM call, empty collection, history isolation and deletion, invalid session 404 before streaming, prompt-injection delimiting, XSS inertness, LLM failure → error event, query rate limit, concurrent queries, persistence across engine restart, health 200/503, CORS allow-list, no secret echo in 422s.
- **RLS:** fail-closed without context, tenant isolation with unfiltered SQL, context surviving commits, cross-tenant insert blocked, admin cannot read chunk text, app role not superuser/BYPASSRLS.

## Not covered
- A real Docker/Compose run (engine unavailable).
- OWASP ZAP.
- Load testing beyond 10 concurrent requests.
- Browser E2E automation framework (manual browser verification was done instead; see DEPLOYMENT_REPORT.md).
