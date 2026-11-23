# Production Readiness Report: Vellum RAG

**Date:** 2026-11-22 · **Branch:** `main` (merged with `origin/main`, committed locally, **not pushed**) · **Deployed:** ✅ https://vellum-rag.vercel.app (Vercel, verified end-to-end, see DEPLOYMENT_REPORT §7)

## Verdict

**The code is ready to deploy. The live environment is not, until you complete the manual security actions below.**

The application is now ready for production use: it is secure, tested and verified in Docker. Three things remain before it should go live:
1. The live Render and Supabase environment still carries the old, exploitable configuration and needs your manual rotation steps (§1).
2. Groq free-tier quotas limit both capacity and today's LLM-judged evaluation (§4).
3. Deployment itself is waiting for your go-ahead (§6).

---

## 1. Security

| Area | Status | Evidence |
|---|---|---|
| Critical findings (shared guest account, forgeable JWT, default admin, retired LLM) | **Fixed + verified in code** | Original code 6/6 vulnerable → fixed 0/6 (`reports/security/original_vs_fixed.json`) |
| High/medium findings (private storage, SSRF, rate limits, prompt injection, cookie sessions + CSRF, upload validation, CORS, headers, MFA, Argon2id, RLS, log redaction) | **Fixed + verified** | SECURITY_AUDIT.md §1 (each row lists its test) |
| Static analysis | Bandit 0 · Semgrep 3 reviewed (false positive / accepted) · pip-audit 0/106 · npm audit 0 | `reports/security/summary.json` |
| Secret scanning | No live secret in git history or the frontend. The Groq and Supabase keys exist only in the gitignored `.env` | detect-secrets + targeted history grep |
| Dynamic probe | 25/25 dev server · **25/25 through the Docker gateway** | `reports/security/dast_probe*.json` |
| OWASP ZAP | **Not run** (needs a CI or ZAP container) | Command in SECURITY_AUDIT §2 |

### ⚠️ Requires your manual action (I have no Render or Supabase dashboard access)
1. **Render → Backend → Environment:** set a new `JWT_SECRET_KEY`. Generate it yourself:
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Also set `ENVIRONMENT=production`. The new code refuses to start without a strong secret.
2. **Supabase → `users` table:** delete `admin@vellum.ai` or set a strong password. I could not verify the live account: the project did not respond, and may be **paused**.
3. **Supabase → Storage → `documents` → Private.** Do this **together with** the new deploy. The old live code needs public URLs, so doing it earlier breaks uploads on the live site.
4. **Rotate the Supabase `service_role` key** if `.env` was ever shared. It has not been in git. Then update Render and your local `.env`.
5. Treat documents previously uploaded through guest mode or the public bucket as exposed.
6. Your local `.env` still sets `POSTGRES_PASSWORD` to the old public default (`docker-compose` only; your Supabase `DATABASE_URL` is separate). Change it if you use the old local Compose volumes, and change the Supabase DB password if it ever matched.

**Done locally.** Your `.env` JWT secret, which was the public default, was replaced with a new random value. It was never printed.

## 2. Docker (verified)

`docker compose up` was run with an isolated env file and project name, so the production Supabase settings were never used.

- **5/5 containers healthy**: postgres, redis, **backend (RAG)**, frontend, nginx.
- Non-root: backend uid 10001, nginx uid 101.
- Only `:8080` is published.
- End to end through the gateway: upload → index (34 chunks) → **grounded, cited answer**; an off-topic question is refused without an LLM call.
- DAST 25/25.
- Vectors persisted across a Postgres and backend restart.

Details are in DEPLOYMENT_REPORT §3b. The stack is still running at http://localhost:8080. Stop it with:
```
docker compose -p vellum-verify --env-file .env.docker.local down
```

**Note.** Your old Compose volumes (`rag_postgres_data` etc.) were left untouched. They use the old DB user and password; see DEPLOYMENT_REPORT §3b before reusing them.

## 3. Testing

| Suite | Result |
|---|---|
| Offline (unit, API/integration/security/RLS/reliability, Gloss) | **98 / 98 pass** |
| Live against Groq (grounding, refusal, indirect prompt injection, DeepEval assertion) | **4 / 4 pass** |
| Frontend typecheck + production build | pass, no source maps |
| Browser checks (dev and production builds) | upload, index, cited answer, sign-in, no JS-readable token |

Not covered: ZAP, load tests beyond 10 concurrent requests, an automated browser E2E framework.

## 4. RAG evaluation

| Measurement | Coverage | Result |
|---|---|---|
| Retrieval hit@5 / MRR@5 (judge-free) | 21 Q | original 0.905 / 0.770 → **0.952 / 0.873** |
| Out-of-scope questions answered from outside knowledge | 25 Q | original **3/3** → **0/3** |
| Citation rate on answers | 25 Q | 45% → **100%** |
| False refusals | 20 answerable | 1 (q01, known retrieval miss) |
| Evidently drift (improved vs original) | 25 Q | 9/16 signals drifted as expected (answers, contexts, citations); questions stable |
| Phoenix tracing | 25 Q | 25/25 complete traces, **0 secrets** in spans |
| TruLens RAG triad (live) | 2 Q | context relevance 0.73 · groundedness 1.00 · answer relevance 0.83 (all ≥ thresholds) |
| DeepEval | calibration + partial | Judge calibration correct (grounded 1.0 vs fabricated 0.0). q08 answer relevancy / precision / recall 1.0; q01 recall 0.0 (known miss) |
| Ragas | validated only | Full scores pending. Groq daily quota exhausted on all usable judge models |

**Option B (agreed):** the full 25-question judged rerun for both pipelines happens after the Groq quota resets. The command is in PROJECT_PROGRESS.md. `allam-2-7b` was tried as a fallback judge and **rejected**: it scored a correct answer 0.0.

## 5. Git status

- **`origin/main` merged.** Your 5 GitHub commits from Nov 10–13 (secret/default-admin removal, **Gloss**, the new theme, the frontend lockfile) are merged into local `main`.
  - Where both sides changed the security code, the stricter rewrite was kept: Argon2id instead of bcrypt's 72-byte limit; production refuses weak secrets instead of falling back.
  - **Gloss now understands the numbered `[n]` citations** of the new pipeline (and still the old `[file, Page N]` form). It is streamed as a `gloss` SSE event, recomputed on `/api/history`, and shown in the chat UI.
  - Verified: 98 tests incl. your `test_gloss.py`, a Docker rebuild, and an end-to-end answer whose claim Gloss rated *supported*. DAST 25/25.
  - `tests/test_auth.py` (old bcrypt helpers) was removed; its coverage moved to `tests/unit/test_security_units.py`.
  - `backend/app.log` was untracked.

- Committed to `main` (the branch you specified). **Not pushed.**
- Excluded from the commit:
  - `.env`, `.env.docker.local` (secrets)
  - `Vellum_RAG_Interview_Masterclass.pdf` (your file in the repo root; a copy is in the frozen eval corpus)
  - `.claude/` (local tooling)
  - large or local evaluation artefacts (Phoenix DB, Evidently workspace, TruLens SQLite)
- A secret scan of the staged changes was run before committing.

## 6. Deployment readiness

| Prerequisite | Status |
|---|---|
| Production config (Dockerfiles, Compose, nginx, `.env.example`, lock files) | ✅ |
| Startup guards (refuses insecure config) | ✅ verified |
| Health checks (`/api/health` 200/503, `/api/health/live`) | ✅ verified |
| Live secrets rotated / admin fixed / bucket private | ⚠️ **your action (§1)** |
| Supabase project active (it appeared paused) | ⚠️ **check** |
| Groq capacity: free tier ≈ 130 answers/day on the primary model | ⚠️ upgrade the tier for real traffic |
| Cookie setup for Render (same-origin rewrite or `COOKIE_SAMESITE=none`) | ⚠️ choose (DEPLOYMENT_REPORT §4) |
| Push + Render deploy | ⏸ **awaiting your explicit approval** |

**Recommended order:**
1. Resume or verify the Supabase project.
2. Rotate the secrets and fix the admin account.
3. Approve the push.
4. Deploy the backend and frontend.
5. Make the bucket private.
6. Run the post-deploy checks (DEPLOYMENT_REPORT §4).
7. Run the full evaluation once the quota resets.

## 7. Live status (2026-11-23)

- **Live:** https://vellum-rag.vercel.app (Vercel Services, backend in Tokyo, Supabase DB and private storage). Verified end to end.
- **Done since the readiness review:**
  - Supabase bucket made **private**.
  - A new JWT secret is in use on Vercel.
  - Sign in with Google implemented (needs your Client ID).
- **Still needs you:**
  1. **Google Client ID:** create an OAuth "Web application" client with authorised JavaScript origin `https://vellum-rag.vercel.app`, then send me the ID (it is public). I'll set `GOOGLE_CLIENT_ID` and redeploy.
  2. **Suspend or delete the old Render service**, which still runs the old, vulnerable code.
  3. Optional: rotate the Supabase `service_role` key (Supabase → Settings → API), then update the Vercel env var.
  4. Optional: add Upstash Redis for rate limits shared across instances.
