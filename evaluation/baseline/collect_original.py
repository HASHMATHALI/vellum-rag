"""Collect baseline records from the ORIGINAL pipeline (commit 20c2aef) for before/after comparison.

The original code is used unchanged except for the model name: `llama-3.3-70b-versatile` is no longer served by
Groq (HTTP 404), so without a substitution the baseline would contain only error messages. The same generation
model as the improved pipeline (openai/gpt-oss-120b) is used so the comparison isolates retrieval/prompt changes.
Original behaviour kept: semantic search (UI default), k=5, 1500/200 chunks, original SYSTEM_RAG_PROMPT (with its
general-knowledge fallback), no threshold, no reranking.

Prerequisite: the corpus ingested by the original code (evaluation/retrieval_benchmark.py --impl original ...).
    git worktree add <dir> 20c2aef
    python evaluation/baseline/collect_original.py --code-dir <dir>/backend --db-url <asyncpg url of rag_baseline>
"""
import argparse
import asyncio
import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-dir", required=True)
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    ap.add_argument("--run-name", default="baseline-original-" + datetime.datetime.now().strftime("%Y%m%d-%H%M"))
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from evaluation.evaluation_config import groq_api_key
    os.environ.update({"DATABASE_URL": args.db_url, "SUPABASE_URL": "", "SUPABASE_KEY": "", "REDIS_URL": "",
                       "GROQ_API_KEY": groq_api_key()})
    sys.path.insert(0, args.code_dir)
    os.chdir(args.code_dir)
    from sqlalchemy import select
    from app.database.connection import async_session
    from app.models.user import User
    from app.models.document import Document
    from app.models.chat import ChatSession  # noqa: F401
    from app.retrieval.retriever import Retriever
    from app.llm.groq_client import groq_client
    from app.prompts.rag_prompts import SYSTEM_RAG_PROMPT

    samples = json.loads((ROOT / "evaluation" / "datasets" / "eval_dataset.json").read_text(encoding="utf-8"))["samples"]
    out_dir = ROOT / "evaluation" / "reports" / "runs" / args.run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == "bench@example.com"))).scalars().first()
        doc_ids = list((await db.execute(select(Document.id).where(Document.user_id == user.id))).scalars().all())
        names = {d.id: d.filename for d in (await db.execute(select(Document))).scalars().all()}
    with open(out_dir / "records.jsonl", "w", encoding="utf-8") as fh:
        for s in samples:
            t0 = time.perf_counter()
            async with async_session() as db:
                res = await Retriever.semantic_search(db, s["question"], k=5, document_ids=doc_ids)
            t_ret = (time.perf_counter() - t0) * 1000
            blocks = [f"[Source: {names.get(c.document_id)}, Page: {c.page_number}]\n{c.text_content}\n" for c, _ in res]
            msgs = [{"role": "system", "content": SYSTEM_RAG_PROMPT.format(context_text="\n".join(blocks) or "No context available.")},
                    {"role": "user", "content": s["question"]}]
            t1 = time.perf_counter()
            answer = "".join([tok async for tok in groq_client.stream_chat_completion(msgs, model=args.model)])
            rec = {"id": s["id"], "category": s["category"], "question": s["question"], "ground_truth": s["ground_truth"],
                   "expected_sources": s.get("expected_sources", []), "evidence": s.get("evidence", []),
                   "answer": answer, "contexts": [c.text_content for c, _ in res],
                   "sources": [{"document_id": c.document_id, "filename": names.get(c.document_id),
                                "page_number": c.page_number, "similarity_score": float(sc)} for c, sc in res],
                   "meta": {"model": args.model, "timings_ms": {"retrieval_ms": round(t_ret, 1),
                                                                 "generation_ms": round((time.perf_counter() - t1) * 1000, 1),
                                                                 "total_ms": round((time.perf_counter() - t0) * 1000, 1)},
                            "validation": {"is_refusal": "general knowledge" in answer.lower()[:200]}},
                   "error": None, "wall_ms": round((time.perf_counter() - t0) * 1000, 1), "mode": "semantic", "k": 5,
                   "pipeline": "original-20c2aef"}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[baseline] {s['id']} {len(answer)} chars")
            await asyncio.sleep(3)
    print("wrote", out_dir / "records.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
