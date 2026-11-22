"""Shared data collection for all evaluation frameworks.

`collect_records()` runs every dataset question through the *real* RAG pipeline (same code as POST /api/query:
reformulation, authorised retrieval, reranking, context building, Groq generation, citation validation) and
writes one JSON record per question. Ragas, DeepEval, TruLens and Evidently all consume these records, so the
frameworks evaluate identical answers and contexts.
"""
import argparse
import asyncio
import datetime
import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

from evaluation.evaluation_config import (CORPUS_DIR, DATASET_PATH, EVAL_USER_EMAIL, RUNS_DIR, configure_backend_env)

configure_backend_env()

from sqlalchemy import delete, select  # noqa: E402

from app.database.connection import async_session, engine, system_session  # noqa: E402
from app.database.migrations import run_migrations  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.user import User  # noqa: E402
from app.rag.pipeline import pipeline  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402

MIME = {"pdf": "application/pdf", "md": "text/markdown", "txt": "text/plain", "csv": "text/csv",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def load_dataset(limit: Optional[int] = None, categories: Optional[List[str]] = None) -> List[dict]:
    samples = json.loads(Path(DATASET_PATH).read_text(encoding="utf-8"))["samples"]
    if categories:
        samples = [s for s in samples if s["category"] in categories]
    return samples[:limit] if limit else samples


async def get_eval_user() -> User:
    async with system_session() as db:
        user = (await db.execute(select(User).where(User.email == EVAL_USER_EMAIL))).scalars().first()
        if user is None:
            user = User(email=EVAL_USER_EMAIL, hashed_password="!unusable", full_name="Evaluation runner", role="user")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user


async def ingest_corpus(fresh: bool = False) -> Tuple[User, dict]:
    """Ingest every corpus file for the eval user through DocumentService.index_bytes (the API ingestion path)."""
    await run_migrations(engine)
    user = await get_eval_user()
    timings = {}
    async with system_session() as db:
        if fresh:
            await db.execute(delete(Document).where(Document.user_id == user.id))
            await db.commit()
        existing = {d.filename for d in (await db.execute(select(Document).where(
            Document.user_id == user.id, Document.status == "indexed"))).scalars().all()}
        for f in sorted(Path(CORPUS_DIR).iterdir()):
            if f.name in existing:
                continue
            ext = f.suffix.lower().strip(".")
            data = f.read_bytes()
            doc = Document(filename=f.name, filepath=f"eval:{f.name}", file_type=ext, file_size=len(data),
                           user_id=user.id, status="processing")
            db.add(doc)
            await db.commit()
            t0 = time.perf_counter()
            n = await DocumentService.index_bytes(db, doc, data)
            timings[f.name] = {"chunks": n, "seconds": round(time.perf_counter() - t0, 3), "bytes": len(data)}
    return user, timings


def phoenix_available(endpoint: str) -> bool:
    import httpx
    base = endpoint.split("/v1/")[0]
    try:
        return httpx.get(base + "/healthz", timeout=3).status_code == 200
    except Exception:
        return False


async def collect_records(limit: Optional[int] = None, mode: str = "hybrid", k: int = 5, run_name: Optional[str] = None,
                          delay_s: float = 0.0, trace: bool = True) -> Path:
    from opentelemetry import trace as otel_trace
    from app.observability import tracing
    from evaluation.evaluation_config import PHOENIX_ENDPOINT
    traced = trace and phoenix_available(PHOENIX_ENDPOINT) and tracing.setup_tracing(
        endpoint=PHOENIX_ENDPOINT, service_name="vellum-rag-eval", force=True)
    print(f"[collect] Phoenix tracing: {'on -> ' + PHOENIX_ENDPOINT if traced else 'off'}")
    user, ingest_t = await ingest_corpus()
    samples = load_dataset(limit)
    run_name = run_name or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "records.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for s in samples:
            t0 = time.perf_counter()
            error = None
            with tracing.span("eval.sample", "CHAIN", {"eval.sample_id": s["id"], "eval.category": s["category"],
                                                        "eval.run": run_name}) as sp:
                trace_id = format(sp.get_span_context().trace_id, "032x") if traced else None
                async with async_session() as db:
                    try:
                        res = await pipeline.answer(db, user.id, s["question"], mode=mode, k=k)
                        rec_answer, contexts, sources, meta = res.answer, res.contexts, res.sources, res.meta
                    except Exception as e:  # recorded, not hidden
                        rec_answer, contexts, sources, meta, error = "", [], [], {}, f"{type(e).__name__}: {e}"
            rec = {
                "id": s["id"], "category": s["category"], "question": s["question"], "ground_truth": s["ground_truth"],
                "expected_sources": s.get("expected_sources", []), "evidence": s.get("evidence", []),
                "answer": rec_answer, "contexts": contexts,
                "sources": [{k_: v for k_, v in src.items() if k_ != "text_content"} for src in sources],
                "meta": meta, "error": error, "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
                "mode": mode, "k": k, "trace_id": trace_id,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[collect] {s['id']} {s['category']:<18} ctx={len(contexts)} "
                  f"refusal={meta.get('validation', {}).get('is_refusal')} {rec['wall_ms']:.0f}ms {error or ''}")
            if delay_s:
                await asyncio.sleep(delay_s)
    (out_dir / "ingestion.json").write_text(json.dumps(ingest_t, indent=1), encoding="utf-8")
    if traced:
        tracing.shutdown_tracing()
    print(f"[collect] wrote {path}")
    return path


def read_records(path) -> List[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def latest_run() -> Path:
    runs = sorted([p for p in RUNS_DIR.iterdir() if (p / "records.jsonl").exists()], key=lambda p: p.stat().st_mtime)
    if not runs:
        raise FileNotFoundError("No evaluation runs found; run evaluation/run_all_evaluations.py first.")
    return runs[-1] / "records.jsonl"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the dataset through the real RAG pipeline and save records")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--run-name")
    ap.add_argument("--mode", default="hybrid")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between questions (Groq rate limits)")
    ap.add_argument("--no-trace", action="store_true")
    a = ap.parse_args()
    asyncio.run(collect_records(a.limit, a.mode, a.k, a.run_name, a.delay, trace=not a.no_trace))
