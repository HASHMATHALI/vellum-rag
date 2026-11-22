# Project Progress (checkpoint)

**Last updated:** 2026-11-22
Read this first when resuming. The current overall status is in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

## Done (verified)
- **Audit, backend and frontend rewrite, security hardening.** See PROJECT_AUDIT.md and SECURITY_AUDIT.md.
- **Tests:** 88 offline + 4 live pass. RLS verified.
- **Security tooling:** DAST 25/25 on the dev server and 25/25 through the Docker gateway. Original-vs-fixed reproduction: 6/6 → 0/6.
- **Docker:** `docker compose` stack built and verified (5/5 healthy, RAG end-to-end, persistence across restarts). It is still running as project `vellum-verify` on http://localhost:8080. Stop it with:
  ```
  docker compose -p vellum-verify --env-file .env.docker.local down
  ```
- **Local secrets:** the local `.env` JWT secret (which was the public default) is rotated. `.env.docker.local` holds the test-stack secrets (gitignored).
- **Evaluation:**
  - complete: judge-free retrieval and behaviour (25 Q); Evidently drift (25 Q); Phoenix traces (25/25, 0 secrets)
  - partial: TruLens (2 Q); DeepEval (calibration + a few observed metrics)
  - pending: Ragas (validated, full scores pending)
- **Git:** committed to `main` (not pushed).

## Agreed next steps
1. **Tomorrow, after the Groq quota resets (option B):** full 25-question judged evaluation for both pipelines:
   ```
   .venv-eval/Scripts/python.exe evaluation/run_all_evaluations.py --records evaluation/reports/runs/final-v2/records.jsonl --parallel
   .venv-eval/Scripts/python.exe evaluation/ragas_evaluation.py --records evaluation/reports/runs/baseline-original/records.jsonl
   ```
   Then update §4 of RAG_EVALUATION_REPORT.md. Use gpt-oss-20b / qwen judges, **not** allam-2-7b (rejected as a judge).
2. **Your manual actions:** the live security items in SECURITY_AUDIT.md §0 "Status".
3. **Push / deploy to Render:** only after your explicit approval (DEPLOYMENT_REPORT.md §4).

## Open quality items
- q01 retrieval miss (small cross-encoder).
- Ambiguous questions get a refusal instead of a clarifying question.
- Throughput is CPU-bound by reranking (~0.8 req/s per 4-core worker).
