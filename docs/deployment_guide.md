# Deployment Guide

The verified status, step-by-step Render instructions, the Docker Compose procedure and the remaining risks are in [DEPLOYMENT_REPORT.md](../DEPLOYMENT_REPORT.md).

Checklist:
1. Rotate secrets and default credentials ([SECURITY_AUDIT.md §0](../SECURITY_AUDIT.md)).
2. Set `ENVIRONMENT=production`, `JWT_SECRET_KEY`, `DATABASE_URL`, `GROQ_API_KEY`, `CORS_ORIGINS`, `COOKIE_SECURE=true`, `REDIS_URL`.
3. Use a **private** storage bucket with a server-side key.
4. Health check path: `/api/health`. The container honours `$PORT` and runs as non-root.
5. Optional: apply `backend/app/database/rls.sql` and connect as `vellum_app` with `ENABLE_RLS=true`.
6. After deploy, check `/api/health`, sign-in, upload, ask a question, and confirm sources are shown.
