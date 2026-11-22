"""Retrieval-only benchmark (no LLM calls) used for before/after comparison and chunking/threshold tuning.

Metrics per retrieval mode, computed on answerable questions with `evidence` strings:
  hit@k, MRR@k, precision@k (chunk relevant if it contains any evidence string),
plus for questions with no supporting text (unanswerable/out_of_domain): the top-1 similarity, to tune the
relevance threshold. Latency per query is also recorded.

  # current code (default):
  python evaluation/retrieval_benchmark.py --db-url postgresql+asyncpg://.../rag_eval
  # original code from a git worktree of commit 20c2aef:
  python evaluation/retrieval_benchmark.py --impl original --code-dir <worktree>/backend --db-url .../rag_baseline
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "datasets" / "eval_dataset.json"
CORPUS = ROOT / "evaluation" / "datasets" / "corpus"


def is_relevant(text: str, evidence: list) -> bool:
    t = " ".join(text.lower().split())
    return any(e in t for e in evidence)


def score_run(samples, results, k):
    """results: {qid: [(text, score), ...]}"""
    rows, hits, mrrs, precs, neg_top = [], [], [], [], []
    for s in samples:
        res = results.get(s["id"], [])
        if s["evidence"]:
            rel = [is_relevant(t, s["evidence"]) for t, _ in res[:k]]
            hit = any(rel)
            rr = next((1.0 / (i + 1) for i, r in enumerate(rel) if r), 0.0)
            prec = (sum(rel) / len(rel)) if rel else 0.0
            hits.append(hit); mrrs.append(rr); precs.append(prec)
            rows.append({"id": s["id"], "hit": hit, "rr": round(rr, 3), "precision": round(prec, 3), "n": len(res)})
        elif s["category"] in ("unanswerable", "out_of_domain"):
            top = res[0][1] if res else None
            neg_top.append(top)
            rows.append({"id": s["id"], "top_score": top, "n": len(res)})
    pos_top = [results[s["id"]][0][1] for s in samples if s["evidence"] and results.get(s["id"])]
    return {
        "hit@k": round(sum(hits) / len(hits), 3) if hits else None,
        "mrr@k": round(sum(mrrs) / len(mrrs), 3) if mrrs else None,
        "precision@k": round(sum(precs) / len(precs), 3) if precs else None,
        "n_answerable": len(hits),
        "answerable_top1_score_min": round(min(pos_top), 3) if pos_top else None,
        "answerable_top1_score_median": round(statistics.median(pos_top), 3) if pos_top else None,
        "negative_top1_scores": [round(x, 3) if x is not None else None for x in neg_top],
        "negative_n_returned": [r["n"] for r in rows if "top_score" in r],
        "per_question": rows,
    }


async def run_original(code_dir, db_url, k, modes):
    os.environ.update({"DATABASE_URL": db_url, "SUPABASE_URL": "", "SUPABASE_KEY": "", "GROQ_API_KEY": "",
                       "REDIS_URL": "", "UPLOAD_DIR": str(Path(code_dir) / "uploads")})
    sys.path.insert(0, str(code_dir))
    os.chdir(code_dir)
    from sqlalchemy import text, delete
    from app.database.base import Base
    from app.database.connection import engine, async_session
    from app.models.user import User
    from app.models.document import Document, DocumentChunk
    from app.models.chat import ChatSession, ChatMessage  # noqa: F401
    from app.ingestion.parser import FileParser
    from app.ingestion.chunker import TextChunker
    from app.embeddings.embedder import embedder
    from app.retrieval.retriever import Retriever

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    ingest_t = {}
    async with async_session() as db:
        u = User(email="bench@example.com", hashed_password="x", full_name="bench", role="user")
        db.add(u); await db.commit(); await db.refresh(u)
        doc_ids = []
        for f in sorted(CORPUS.iterdir()):
            ext = f.suffix.lower().strip(".")
            if ext not in ("pdf", "docx", "txt", "md"):
                ingest_t[f.name] = "unsupported by original code"
                continue
            t0 = time.perf_counter()
            pages = FileParser.parse(str(f), ext)
            chunks = TextChunker().chunk_document(pages)
            d = Document(filename=f.name, filepath=str(f), file_type=ext, file_size=f.stat().st_size,
                         user_id=u.id, status="indexed", total_chunks=len(chunks))
            db.add(d); await db.flush()
            embs = embedder.get_embeddings([c["text_content"] for c in chunks])
            for c, e in zip(chunks, embs):
                db.add(DocumentChunk(document_id=d.id, chunk_index=c["chunk_index"], text_content=c["text_content"],
                                     page_number=c["page_number"], embedding=e.tolist()))
            await db.commit()
            ingest_t[f.name] = {"chunks": len(chunks), "seconds": round(time.perf_counter() - t0, 3)}
            doc_ids.append(d.id)

    async def search(mode, q):
        async with async_session() as db:
            fn = {"semantic": Retriever.semantic_search, "mmr": Retriever.mmr_search, "hybrid": Retriever.hybrid_search}[mode]
            res = await fn(db, q, k=k, document_ids=doc_ids)
            return [(c.text_content, float(s)) for c, s in res]

    return ingest_t, search


async def run_current(db_url, k, modes):
    os.environ["EVAL_DATABASE_URL"] = db_url
    sys.path.insert(0, str(ROOT / "backend"))
    from evaluation.common import ingest_corpus
    from app.database.connection import async_session
    from app.retrieval.retriever import Retriever

    user, ingest_t = await ingest_corpus(fresh=True)

    async def search(mode, q):
        base, _, rr = mode.partition("+")
        async with async_session() as db:
            res = await Retriever.search(db, q, user_id=user.id, mode=base, k=k, apply_threshold=False,
                                         use_reranker=rr == "rerank")
            return [(r.text, r.score) for r in res]

    return ingest_t, search


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", choices=["original", "current"], default="current")
    ap.add_argument("--code-dir")
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--modes", default="semantic,mmr,hybrid,semantic+rerank,hybrid+rerank")
    ap.add_argument("--out")
    args = ap.parse_args()
    modes = args.modes.split(",")
    samples = json.loads(DATASET.read_text(encoding="utf-8"))["samples"]
    sys.path.insert(0, str(ROOT))
    if args.impl == "original":
        ingest_t, search = await run_original(Path(args.code_dir), args.db_url, args.k, modes)
    else:
        ingest_t, search = await run_current(args.db_url, args.k, modes)

    report = {"impl": args.impl, "k": args.k, "ingestion": ingest_t, "modes": {}}
    for mode in modes:
        results, lat = {}, []
        await search(mode, "warm up query")
        for s in samples:
            t0 = time.perf_counter()
            results[s["id"]] = await search(mode, s["question"])
            lat.append((time.perf_counter() - t0) * 1000)
        r = score_run(samples, results, args.k)
        r["latency_ms_p50"] = round(statistics.median(lat), 1)
        r["latency_ms_max"] = round(max(lat), 1)
        report["modes"][mode] = r
        print(f"{args.impl:8s} {mode:8s} hit@{args.k}={r['hit@k']} mrr={r['mrr@k']} p@k={r['precision@k']} "
              f"p50={r['latency_ms_p50']}ms neg_top1={r['negative_top1_scores']}")
    out = Path(args.out) if args.out else ROOT / "evaluation" / "reports" / f"retrieval_{args.impl}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    asyncio.run(main())
