"""Run the backend locally against the embedded Postgres (scripts/local_postgres.py).

Only GROQ_API_KEY is taken from the repository .env; DATABASE_URL/SUPABASE_* are deliberately NOT read from it,
so local runs can never touch the production database or bucket.

    python scripts/dev_server.py [--db rag_dev] [--port 8000] [--trace]
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def local_db_url(db: str) -> str:
    out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "local_postgres.py"), db], text=True)
    return [l for l in out.splitlines() if l.startswith(db + "=")][0].split("=", 1)[1]


def groq_key() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GROQ_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("GROQ_API_KEY", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="rag_dev")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--trace", action="store_true", help="export OpenTelemetry spans to Phoenix on :6006")
    args = ap.parse_args()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DATABASE_URL", "SUPABASE"))}
    env.update({
        "DATABASE_URL": local_db_url(args.db), "SUPABASE_URL": "", "SUPABASE_KEY": "",
        "GROQ_API_KEY": groq_key(), "ENVIRONMENT": env.get("ENVIRONMENT", "development"),
        "COOKIE_SECURE": env.get("COOKIE_SECURE", "false"), "UPLOAD_DIR": str(ROOT / "backend" / "uploads"),
        "CORS_ORIGINS": env.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"),
    })
    if args.trace:
        env.update({"OTEL_ENABLED": "true", "TRACE_INCLUDE_CONTENT": "true"})
    os.chdir(ROOT / "backend")
    sys.exit(subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                              "--port", str(args.port)], env=env))


if __name__ == "__main__":
    main()
