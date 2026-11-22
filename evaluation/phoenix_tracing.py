"""Arize Phoenix: verify end-to-end traces of an evaluation run, attach evaluation scores, check trace privacy.

The pipeline exports OpenInference-style OpenTelemetry spans (app/observability/tracing.py):
  eval.sample (CHAIN) -> rag.query (CHAIN) -> rag.reformulate (LLM, follow-ups only) -> rag.retrieve (RETRIEVER)
  -> rag.generate (LLM: model, token counts, prompt/response when TRACE_INCLUDE_CONTENT=true)

This script, for the run's records:
  1. fetches the spans from Phoenix and checks every record has a complete trace (retriever + LLM or skip reason);
  2. computes per-stage latency from span timings;
  3. logs Ragas / DeepEval scores as span annotations on each request's root span (visible in the Phoenix UI);
  4. scans exported span attributes for secrets (API keys, JWTs, passwords).

Start Phoenix first:  python -m phoenix.server.main serve   (UI: http://127.0.0.1:6006)
    python evaluation/phoenix_tracing.py [--records ...]
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phoenix.client import Client  # noqa: E402

from evaluation.evaluation_config import PHOENIX_ENDPOINT  # noqa: E402
from evaluation.ragas_evaluation import latest_records, read_records  # noqa: E402

PROJECT = "vellum-rag-eval"
SECRET_PATTERNS = [re.compile(p) for p in (r"gsk_[A-Za-z0-9]{20,}", r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.",
                                           r"(?i)password\s*[:=]\s*\S+", r"sk-[A-Za-z0-9]{20,}",
                                           r"postgres(ql)?(\+asyncpg)?://[^:\s]+:[^@\s]+@")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records")
    args = ap.parse_args()
    path = Path(args.records) if args.records else latest_records()
    records = read_records(path)
    base = PHOENIX_ENDPOINT.split("/v1/")[0]
    client = Client(base_url=base)
    spans = client.spans.get_spans_dataframe(project_identifier=PROJECT, limit=20000)
    trace_ids = {r["trace_id"] for r in records if r.get("trace_id")}
    spans = spans[spans["context.trace_id"].isin(trace_ids)].copy()
    print(f"[phoenix] {len(spans)} spans for {len(trace_ids)} traced records")

    spans["duration_ms"] = (pd.to_datetime(spans["end_time"]) - pd.to_datetime(spans["start_time"])).dt.total_seconds() * 1000
    stage_latency = {name: {"p50_ms": round(float(g["duration_ms"].median()), 1),
                            "max_ms": round(float(g["duration_ms"].max()), 1), "count": int(len(g))}
                     for name, g in spans.groupby("name")}

    # completeness per record
    completeness = []
    for r in records:
        tid = r.get("trace_id")
        names = set(spans.loc[spans["context.trace_id"] == tid, "name"]) if tid else set()
        skipped = (r.get("meta") or {}).get("generation_skipped")
        complete = {"rag.query", "rag.retrieve"} <= names and ("rag.generate" in names or bool(skipped))
        completeness.append({"id": r["id"], "trace_id": tid, "spans": sorted(names), "complete": complete,
                             "generation_skipped": skipped})

    # token usage recorded on LLM spans
    tok_col = "attributes.llm.token_count.total"
    tokens = spans[tok_col].dropna().astype(float) if tok_col in spans else pd.Series(dtype=float)

    # privacy scan over every exported attribute value
    leaks = []
    attr_cols = [c for c in spans.columns if c.startswith("attributes.")]
    for _, row in spans.iterrows():
        for c in attr_cols:
            v = row[c]
            if isinstance(v, (list, dict)):
                v = json.dumps(v, default=str)
            if isinstance(v, str) and any(p.search(v) for p in SECRET_PATTERNS):
                leaks.append({"span": row["name"], "attribute": c})

    # attach evaluation scores to the root span of each request
    annotations = []
    roots = spans[spans["name"] == "eval.sample"].set_index("context.trace_id")
    run_dir = path.parent
    for fw, file, key in (("ragas", run_dir / "ragas" / "ragas_results.json", "per_sample"),
                          ("deepeval", run_dir / "deepeval" / "deepeval_results.json", "per_sample")):
        if not file.exists():
            continue
        for row in json.loads(file.read_text(encoding="utf-8"))[key]:
            rec = next((r for r in records if r["id"] == row["id"]), None)
            if not rec or rec.get("trace_id") not in roots.index:
                continue
            span_id = roots.loc[rec["trace_id"], "context.span_id"]
            for metric, score in row.get("scores", {}).items():
                if score is not None:
                    annotations.append({"span_id": span_id, "name": f"{fw}.{metric}", "annotator_kind": "LLM",
                                        "result": {"score": float(score)}, "metadata": {"framework": fw}})
    logged = 0
    if annotations:
        try:
            client.spans.log_span_annotations(span_annotations=annotations, sync=True)
            logged = len(annotations)
        except Exception as e:
            print(f"[phoenix] annotation logging failed: {type(e).__name__}: {str(e)[:200]}")

    out = {
        "phoenix_url": base, "project": PROJECT, "records": str(path), "traced_records": len(trace_ids),
        "spans": int(len(spans)), "complete_traces": sum(c["complete"] for c in completeness),
        "incomplete": [c for c in completeness if not c["complete"]],
        "stage_latency": stage_latency,
        "llm_tokens": {"spans_with_usage": int(len(tokens)), "total": int(tokens.sum()) if len(tokens) else 0,
                       "p50_per_call": float(tokens.median()) if len(tokens) else None},
        "secret_leaks": leaks, "annotations_logged": logged,
        "how_to_inspect": f"Open {base} -> project '{PROJECT}' -> filter by attribute eval.sample_id or a trace_id from records.jsonl",
    }
    (run_dir / "phoenix_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "incomplete"}, indent=1))
    print("saved", run_dir / "phoenix_summary.json")


if __name__ == "__main__":
    main()
