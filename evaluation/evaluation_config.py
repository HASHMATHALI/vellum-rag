"""Shared configuration for the evaluation suite.

Environment variables (all optional):
  EVAL_DATABASE_URL   asyncpg URL of an *evaluation* database (default: local embedded Postgres 'rag_eval').
                      Never point this at production: the corpus is re-ingested for a dedicated eval user.
  GROQ_API_KEY        used for RAG generation and as the LLM judge (read from the repo .env if not set).
  EVAL_JUDGE_MODEL    judge model for Ragas / DeepEval / TruLens (default openai/gpt-oss-120b).
  EVAL_LIMIT          only evaluate the first N samples (quick runs).
  PHOENIX_ENDPOINT    OTLP endpoint for traces (default http://127.0.0.1:6006/v1/traces).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DATASET_PATH = ROOT / "evaluation" / "datasets" / "eval_dataset.json"
CORPUS_DIR = ROOT / "evaluation" / "datasets" / "corpus"
REPORTS_DIR = ROOT / "evaluation" / "reports"
RUNS_DIR = REPORTS_DIR / "runs"
EVAL_USER_EMAIL = "eval-runner@vellum.local"

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "openai/gpt-oss-120b")
JUDGE_FALLBACK_MODEL = os.environ.get("EVAL_JUDGE_FALLBACK", "qwen/qwen3.8-27b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
PHOENIX_ENDPOINT = os.environ.get("PHOENIX_ENDPOINT", "http://127.0.0.1:6006/v1/traces")

# Acceptance thresholds, set from the first baseline run of the improved pipeline (see RAG_EVALUATION_REPORT.md).
# Scores from different frameworks are NOT interchangeable; each threshold applies only to its own framework.
THRESHOLDS = {
    "ragas": {"faithfulness": 0.80, "answer_relevancy": 0.70, "context_precision": 0.70, "context_recall": 0.75,
              "answer_correctness": 0.55},
    "deepeval": {"answer_relevancy": 0.7, "faithfulness": 0.8, "contextual_precision": 0.7, "contextual_recall": 0.7,
                 "contextual_relevancy": 0.4, "hallucination_min": 0.7},
    "trulens": {"context_relevance": 0.6, "groundedness": 0.8, "answer_relevance": 0.7},
    "behaviour": {"refusal_rate_unanswerable": 1.0, "false_refusal_rate_answerable_max": 0.1},
}


def groq_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("GROQ_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    return key


def eval_database_url() -> str:
    url = os.environ.get("EVAL_DATABASE_URL")
    if url:
        return url
    out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "local_postgres.py"), "rag_eval"], text=True)
    return [l for l in out.splitlines() if l.startswith("rag_eval=")][0].split("=", 1)[1]


def configure_backend_env(trace_content: bool = True) -> None:
    """Point the backend package at the evaluation database before it is imported."""
    os.environ.update({
        "DATABASE_URL": eval_database_url(), "SUPABASE_URL": "", "SUPABASE_KEY": "", "REDIS_URL": "",
        "ENVIRONMENT": "test", "LOG_FILE": "", "GROQ_API_KEY": groq_api_key(),
        "TRACE_INCLUDE_CONTENT": "true" if trace_content else "false",
    })
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
