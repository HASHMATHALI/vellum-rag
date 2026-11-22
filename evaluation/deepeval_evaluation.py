"""DeepEval evaluation of pipeline records with thresholds, judge calibration and failure reporting.

Metrics: AnswerRelevancy, Faithfulness (penalize_ambiguous_claims=True, so unsupported claims count, not only
contradictions), ContextualPrecision, ContextualRecall, ContextualRelevancy, Hallucination.
Judge: Groq via LiteLLM (EVAL_DEEPEVAL_MODEL, default groq/qwen/qwen3.8-27b).

Before scoring, a small calibration set (one grounded answer, one fabricated answer) checks that the judge can
tell them apart; the result is written to the report. LLM judges are themselves fallible: treat scores as signals,
not ground truth (see RAG_EVALUATION_REPORT.md "Limitations").

    python evaluation/deepeval_evaluation.py [--records ...]
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_RESULTS_FOLDER", "")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepeval.metrics import (AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,  # noqa: E402
                              ContextualRelevancyMetric, FaithfulnessMetric, HallucinationMetric)
from deepeval.models import LiteLLMModel  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

from evaluation.evaluation_config import THRESHOLDS, groq_api_key  # noqa: E402
from evaluation.ratelimit import DailyBudgetExhausted, call_with_retry  # noqa: E402
from evaluation.ragas_evaluation import latest_records, read_records  # noqa: E402

MODEL = os.environ.get("EVAL_DEEPEVAL_MODEL", "groq/qwen/qwen3.8-27b")
# Reasons cost an extra judge call per metric; disable on tight output-token budgets (EVAL_DEEPEVAL_REASONS=0).
REASONS = os.environ.get("EVAL_DEEPEVAL_REASONS", "1") == "1"
FACTUAL = {"answerable", "multi_doc", "hallucination_prone"}
T = THRESHOLDS["deepeval"]


def build_metrics(model):
    return {
        "answer_relevancy": lambda: AnswerRelevancyMetric(include_reason=REASONS, threshold=T["answer_relevancy"], model=model, async_mode=False),
        "faithfulness": lambda: FaithfulnessMetric(include_reason=REASONS, threshold=T["faithfulness"], model=model, async_mode=False,
                                                   penalize_ambiguous_claims=True),
        "contextual_precision": lambda: ContextualPrecisionMetric(include_reason=REASONS, threshold=T["contextual_precision"], model=model, async_mode=False),
        "contextual_recall": lambda: ContextualRecallMetric(include_reason=REASONS, threshold=T["contextual_recall"], model=model, async_mode=False),
        "contextual_relevancy": lambda: ContextualRelevancyMetric(include_reason=REASONS, threshold=T["contextual_relevancy"], model=model, async_mode=False),
        # HallucinationMetric (deepeval >= 4.3): 1 = no contradiction with `context`, 0 = hallucinated; threshold is the
        # MINIMUM passing score. `context` is the reference answer (the metric's intended "ideal context").
        "hallucination": lambda: HallucinationMetric(include_reason=REASONS, threshold=T["hallucination_min"], model=model, async_mode=False),
    }


def measure(metric, tc):
    """Returns (score, success, reason, error). Raises DailyBudgetExhausted so the run can stop and save."""
    t = time.time()
    try:
        call_with_retry(lambda: metric.measure(tc))
        print(f"  [deepeval] {type(metric).__name__} {metric.score} ({time.time() - t:.0f}s)", flush=True)
        return metric.score, metric.success, (metric.reason or "")[:300], None
    except DailyBudgetExhausted:
        raise
    except Exception as e:
        print(f"  [deepeval] {type(metric).__name__} ERROR after {time.time() - t:.0f}s: {type(e).__name__}: {str(e)[:160]}", flush=True)
        return None, None, None, f"{type(e).__name__}: {str(e)[:200]}"


def calibrate(metrics):
    ctx = ["The all-MiniLM-L6-v2 model outputs 384-dimensional vectors.", "The default chunk size is 1500 characters."]
    ref = ["The all-MiniLM-L6-v2 embeddings are 384-dimensional."]
    good = LLMTestCase(input="What is the embedding dimension?", actual_output="The embeddings are 384-dimensional.",
                       retrieval_context=ctx, context=ref, expected_output=ref[0])
    bad = LLMTestCase(input="What is the embedding dimension?",
                      actual_output="The embeddings are 1536-dimensional and were trained by OpenAI in 2019.",
                      retrieval_context=ctx, context=ref, expected_output=ref[0])
    out = {}
    for name in ("faithfulness", "hallucination"):
        g = measure(metrics[name](), good)[0]
        b = measure(metrics[name](), bad)[0]
        ok = g is not None and b is not None and g > b  # both metrics: higher = better in deepeval >= 4.3
        out[name] = {"grounded_case": g, "fabricated_case": b, "discriminates": ok}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records")
    ap.add_argument("--ids", help="comma-separated sample ids")
    args = ap.parse_args()
    path = Path(args.records) if args.records else latest_records()
    records = read_records(path)
    if args.ids:
        keep = set(args.ids.split(","))
        records = [r for r in records if r["id"] in keep]
    # Small max_tokens keeps each request's output-token reservation under Groq's per-minute output cap (qwen: 1,000).
    model = LiteLLMModel(model=MODEL, api_key=groq_api_key(), temperature=0,
                         generation_kwargs={"max_tokens": int(os.environ.get("EVAL_DEEPEVAL_MAX_TOKENS", "700"))})
    metrics = build_metrics(model)
    t0 = time.time()
    out_dir = path.parent / "deepeval"
    out_dir.mkdir(exist_ok=True)
    rows, stopped, calibration = [], None, None

    def save():
        summary = {}
        for n in build_metrics(model):
            vals = [r["scores"][n] for r in rows if r["scores"].get(n) is not None]
            passes = [r["passed"][n] for r in rows if n in r["passed"]]
            summary[n] = {"mean": round(statistics.mean(vals), 4) if vals else None, "n": len(vals),
                          "pass_rate": round(sum(passes) / len(passes), 3) if passes else None}
        failed_cases = [{"id": r["id"], "category": r["category"], "failed": r["failed_metrics"],
                         "reasons": {m: r["reasons"].get(m) for m in r["failed_metrics"]}} for r in rows if r["failed_metrics"]]
        report = {"framework": "deepeval", "sample_ids": [r["id"] for r in records],
                  "completed_ids": [r["id"] for r in rows], "stopped_reason": stopped,
                  "version": __import__("importlib.metadata").metadata.version("deepeval"),
                  "judge_model": MODEL, "thresholds": T, "records": str(path), "seconds": round(time.time() - t0, 1),
                  "calibration": calibration, "summary": summary, "failed_cases": failed_cases, "per_sample": rows}
        (out_dir / "deepeval_results.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        return summary

    try:
        calibration = calibrate(metrics)
    except DailyBudgetExhausted as e:
        stopped = f"judge daily token budget exhausted: {str(e)[:160]}"
    print("[deepeval] calibration:", calibration)

    for rec in records:
        if stopped:
            break
        if rec.get("error"):
            continue
        tc = LLMTestCase(input=rec["question"], actual_output=rec["answer"], expected_output=rec["ground_truth"],
                         retrieval_context=rec["contexts"] or None, context=[rec["ground_truth"]],
                         metadata={"id": rec["id"], "category": rec["category"]})
        names = ["answer_relevancy"]
        if rec["category"] in FACTUAL and rec["contexts"]:
            names += ["faithfulness", "contextual_precision", "contextual_recall", "contextual_relevancy", "hallucination"]
        row = {"id": rec["id"], "category": rec["category"], "scores": {}, "passed": {}, "reasons": {}, "errors": {}}
        try:
            measured = [(n, *measure(metrics[n](), tc)) for n in names]
        except DailyBudgetExhausted as e:
            stopped = f"judge daily token budget exhausted: {str(e)[:160]}"
            print("[deepeval] STOP:", stopped)
            break
        for n, score, success, reason, err in measured:
            if err:
                row["errors"][n] = err
            else:
                row["scores"][n] = round(score, 4) if score is not None else None
                row["passed"][n] = bool(success)
                row["reasons"][n] = reason
        row["failed_metrics"] = [n for n, ok in row["passed"].items() if not ok]
        print(f"[deepeval] {rec['id']} {row['scores']} failed={row['failed_metrics']} {list(row['errors']) or ''}")
        rows.append(row)
        save()  # incremental

    summary = save()
    print(json.dumps(summary, indent=1))
    print("saved", out_dir / "deepeval_results.json")


if __name__ == "__main__":
    main()
