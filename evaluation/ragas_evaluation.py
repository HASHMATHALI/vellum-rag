"""Ragas evaluation (ragas 0.4 "collections" metrics) over records produced by the real pipeline.

Metrics: faithfulness, answer_relevancy, context_precision (with reference), context_recall, answer_correctness,
context_relevance. Judge: Groq (EVAL_RAGAS_MODEL, default openai/gpt-oss-20b) via an OpenAI-compatible client.
Embeddings (answer relevancy / correctness similarity): local all-MiniLM-L6-v2.

Applicability: context-based metrics need retrieved contexts and a factual reference, so they are computed for
answerable / multi_doc / hallucination_prone questions only. For unanswerable / out_of_domain / ambiguous
questions only answer_correctness (does the answer match the expected refusal) is computed.

    python evaluation/ragas_evaluation.py [--records evaluation/reports/runs/<run>/records.jsonl]
"""
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import instructor  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from ragas.embeddings import HuggingFaceEmbeddings  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.metrics.collections import (AnswerCorrectness, AnswerRelevancy, ContextPrecisionWithReference,  # noqa: E402
                                       ContextRecall, ContextRelevance, Faithfulness)

from evaluation.evaluation_config import GROQ_BASE_URL, THRESHOLDS, groq_api_key  # noqa: E402

FACTUAL = {"answerable", "multi_doc", "hallucination_prone"}
MODEL = os.environ.get("EVAL_RAGAS_MODEL", "openai/gpt-oss-20b")


def read_records(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def latest_records() -> Path:
    runs = sorted(Path(__file__).resolve().parent.joinpath("reports", "runs").glob("*/records.jsonl"),
                  key=lambda p: p.stat().st_mtime)
    return runs[-1]


from evaluation.ratelimit import DailyBudgetExhausted, acall_with_retry  # noqa: E402


async def evaluate_record(rec, m, sem):
    scores, errors = {}, {}
    q, a, ctx, ref = rec["question"], rec["answer"], rec["contexts"], rec["ground_truth"]
    jobs = {"answer_correctness": lambda: m["answer_correctness"].ascore(user_input=q, response=a, reference=ref)}
    if rec["category"] in FACTUAL:
        jobs["answer_relevancy"] = lambda: m["answer_relevancy"].ascore(user_input=q, response=a)
        if ctx:
            jobs.update({
                "faithfulness": lambda: m["faithfulness"].ascore(user_input=q, response=a, retrieved_contexts=ctx),
                "context_precision": lambda: m["context_precision"].ascore(user_input=q, reference=ref, retrieved_contexts=ctx),
                "context_recall": lambda: m["context_recall"].ascore(user_input=q, retrieved_contexts=ctx, reference=ref),
                "context_relevance": lambda: m["context_relevance"].ascore(user_input=q, retrieved_contexts=ctx),
            })
        else:
            # No context retrieved for a factual question: recall/precision are zero by definition.
            scores.update({"context_recall": 0.0, "context_precision": 0.0})
    for name, fn in jobs.items():
        async with sem:
            try:
                r = await acall_with_retry(fn)
                v = float(r.value)
                scores[name] = None if math.isnan(v) else round(v, 4)
            except DailyBudgetExhausted:
                raise
            except Exception as e:
                errors[name] = f"{type(e).__name__}: {str(e)[:200]}"
    return {"id": rec["id"], "category": rec["category"], "scores": scores, "errors": errors}


def summarise(rows):
    names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness",
             "context_relevance"]
    out = {}
    for n in names:
        vals = [r["scores"][n] for r in rows if r["scores"].get(n) is not None]
        out[n] = {"mean": round(statistics.mean(vals), 4) if vals else None, "n": len(vals),
                  "threshold": THRESHOLDS["ragas"].get(n)}
        if vals and out[n]["threshold"] is not None:
            out[n]["pass"] = out[n]["mean"] >= out[n]["threshold"]
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    out["_by_category"] = {c: {n: round(statistics.mean(v), 4) for n in names
                               if (v := [x["scores"][n] for x in rs if x["scores"].get(n) is not None])}
                           for c, rs in by_cat.items()}
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--ids", help="comma-separated sample ids (stratified subset to fit LLM rate limits)")
    args = ap.parse_args()
    path = Path(args.records) if args.records else latest_records()
    records = read_records(path)
    if args.ids:
        keep = set(args.ids.split(","))
        records = [r for r in records if r["id"] in keep]
    client = AsyncOpenAI(base_url=GROQ_BASE_URL, api_key=groq_api_key(), max_retries=4, timeout=120)
    llm = llm_factory(MODEL, provider="openai", client=client, mode=instructor.Mode.JSON,
                      max_tokens=int(os.environ.get("EVAL_RAGAS_MAX_TOKENS", "4000")), temperature=0)
    emb = HuggingFaceEmbeddings(model="sentence-transformers/all-MiniLM-L6-v2")
    metrics = {
        "faithfulness": Faithfulness(llm=llm), "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=emb, strictness=1),  # 1 generated question: saves tokens
        "context_precision": ContextPrecisionWithReference(llm=llm), "context_recall": ContextRecall(llm=llm),
        "answer_correctness": AnswerCorrectness(llm=llm, embeddings=emb), "context_relevance": ContextRelevance(llm=llm),
    }
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()
    rows, stopped = [], None
    out_dir = path.parent / "ragas"
    out_dir.mkdir(exist_ok=True)

    def save():
        summary = summarise(rows)
        report = {"framework": "ragas", "sample_ids": [r["id"] for r in records], "completed_ids": [r["id"] for r in rows],
                  "stopped_reason": stopped, "version": __import__("importlib.metadata").metadata.version("ragas"),
                  "judge_model": MODEL, "records": str(path), "seconds": round(time.time() - t0, 1),
                  "summary": summary, "per_sample": rows}
        (out_dir / "ragas_results.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        return summary

    for rec in records:
        if rec.get("error"):
            rows.append({"id": rec["id"], "category": rec["category"], "scores": {}, "errors": {"pipeline": rec["error"]}})
            continue
        try:
            row = await evaluate_record(rec, metrics, sem)
        except DailyBudgetExhausted as e:
            stopped = f"judge daily token budget exhausted: {str(e)[:160]}"
            print("[ragas] STOP:", stopped)
            break
        print(f"[ragas] {row['id']} {row['scores']} {('ERR ' + str(list(row['errors']))) if row['errors'] else ''}")
        rows.append(row)
        save()  # incremental: partial progress survives rate-limit stops
    summary = save()
    print(json.dumps({k: v for k, v in summary.items() if not k.startswith("_")}, indent=1))
    print("saved", out_dir / "ragas_results.json")


if __name__ == "__main__":
    asyncio.run(main())
