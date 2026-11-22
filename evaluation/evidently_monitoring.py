"""Evidently monitoring for RAG inputs, outputs, retrieval and latency.

Sources:
  --records <run>/records.jsonl  (default: latest evaluation run). Judge scores from the same run (Ragas) are merged
                                 when available.
  --db-url <asyncpg url>         monitor real traffic from chat_messages (numeric metadata + text lengths only;
                                 question/answer text is not exported). Use a read-only role.
Reference data (for drift): --reference <records.jsonl>, else the previous run with the same number of samples.

Outputs (in <run>/evidently/): report.html, report.json, plus a snapshot added to a local Evidently workspace
(evaluation/reports/evidently_workspace) and a row appended to evaluation/reports/evidently_history.csv so metrics
can be tracked across runs. View dashboards with:  evidently ui --workspace evaluation/reports/evidently_workspace
"""
import argparse
import asyncio
import csv
import datetime
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidently import DataDefinition, Dataset, Report  # noqa: E402
from evidently.descriptors import Contains, RegExp, SentenceCount, TextLength  # noqa: E402
from evidently.presets import DataDriftPreset, DataSummaryPreset, TextEvals  # noqa: E402

from evaluation.evaluation_config import REPORTS_DIR  # noqa: E402
from evaluation.ragas_evaluation import latest_records, read_records  # noqa: E402

NO_ANSWER_PREFIX = "I couldn't find information about that"
NUMERIC = ["n_contexts", "total_ms", "retrieval_ms", "rerank_ms", "generation_ms", "ttft_ms", "prompt_tokens",
           "completion_tokens", "context_tokens", "top_source_score", "faithfulness", "answer_relevancy",
           "context_precision", "context_recall"]
CATEGORICAL = ["category", "is_refusal", "grounding_warning", "model"]


def records_to_frame(records, ragas_scores=None) -> pd.DataFrame:
    ragas_scores = ragas_scores or {}
    rows = []
    for r in records:
        meta = r.get("meta") or {}
        t = meta.get("timings_ms") or {}
        u = meta.get("usage") or {}
        v = meta.get("validation") or {}
        s = ragas_scores.get(r["id"], {})
        rows.append({
            "id": r["id"], "category": r.get("category", "live"), "question": r.get("question", ""),
            "answer": r.get("answer", ""), "n_contexts": len(r.get("contexts") or r.get("sources") or []),
            "total_ms": t.get("total_ms") or r.get("wall_ms"), "retrieval_ms": t.get("retrieval_ms"),
            "rerank_ms": t.get("rerank_ms"), "generation_ms": t.get("generation_ms"), "ttft_ms": meta.get("ttft_ms"),
            "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
            "context_tokens": (meta.get("retrieval") or {}).get("context_tokens"),
            "top_source_score": max([x.get("similarity_score", 0) for x in r.get("sources", [])], default=None),
            "is_refusal": str(bool(v.get("is_refusal"))), "grounding_warning": str(v.get("grounding_warning")),
            "model": str(meta.get("model")), **{k: s.get(k) for k in ("faithfulness", "answer_relevancy",
                                                                       "context_precision", "context_recall")},
        })
    df = pd.DataFrame(rows)
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


async def frame_from_db(db_url: str, days: int) -> pd.DataFrame:
    """Live-traffic monitoring: numeric metadata only (no question/answer text leaves the database)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    eng = create_async_engine(db_url)
    async with eng.connect() as conn:
        res = await conn.execute(text(
            "SELECT id, length(content) AS answer_len, meta, json_array_length(sources) AS n_src, created_at "
            "FROM chat_messages WHERE role='assistant' AND created_at > now() - make_interval(days => :d)"), {"d": days})
        rows = res.mappings().all()
    await eng.dispose()
    recs = []
    for r in rows:
        meta = r["meta"] if isinstance(r["meta"], dict) else json.loads(r["meta"] or "{}")
        recs.append({"id": r["id"], "category": "live", "question": "", "answer": "x" * int(r["answer_len"] or 0),
                     "sources": [{}] * int(r["n_src"] or 0), "meta": meta})
    return records_to_frame(recs)


def find_reference(current: Path, n: int):
    runs = sorted((REPORTS_DIR / "runs").glob("*/records.jsonl"), key=lambda p: p.stat().st_mtime)
    candidates = [p for p in runs if p.resolve() != current.resolve() and len(read_records(p)) == n]
    return candidates[-1] if candidates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records")
    ap.add_argument("--reference")
    ap.add_argument("--db-url")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    if args.db_url:
        cur = asyncio.run(frame_from_db(args.db_url, args.days))
        out_dir = REPORTS_DIR / "live_monitoring" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        ref, ref_path, run_name = None, None, "live"
    else:
        path = Path(args.records) if args.records else latest_records()
        ragas_file = path.parent / "ragas" / "ragas_results.json"
        scores = {r["id"]: r["scores"] for r in json.loads(ragas_file.read_text(encoding="utf-8"))["per_sample"]} \
            if ragas_file.exists() else {}
        recs = read_records(path)
        cur = records_to_frame(recs, scores)
        ref_path = Path(args.reference) if args.reference else find_reference(path, len(recs))
        ref = None
        if ref_path:
            rf = ref_path.parent / "ragas" / "ragas_results.json"
            rscores = {r["id"]: r["scores"] for r in json.loads(rf.read_text(encoding="utf-8"))["per_sample"]} if rf.exists() else {}
            ref = records_to_frame(read_records(ref_path), rscores)
        out_dir = path.parent / "evidently"
        run_name = path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)

    definition = DataDefinition(id_column="id", text_columns=["question", "answer"],
                                numerical_columns=[c for c in NUMERIC if cur[c].notna().any()],
                                categorical_columns=CATEGORICAL)
    descriptors = [
        TextLength("answer", alias="answer_length"), SentenceCount("answer", alias="answer_sentences"),
        TextLength("question", alias="question_length"),
        Contains("answer", items=[NO_ANSWER_PREFIX], alias="refusal_phrase"),
        RegExp("answer", reg_exp=r"\[\d+\]", alias="has_citation"),
    ]
    cur_ds = Dataset.from_pandas(cur, data_definition=definition, descriptors=descriptors)
    ref_ds = Dataset.from_pandas(ref, data_definition=definition, descriptors=descriptors) if ref is not None else None
    numeric_cols = [c for c in NUMERIC if cur[c].notna().any()]
    descriptor_cols = ["answer_length", "answer_sentences", "question_length", "refusal_phrase", "has_citation"]
    # Raw text is summarised through descriptors; Evidently's TF-IDF text statistics need more rows than a quick run has.
    metrics = [DataSummaryPreset(columns=numeric_cols + CATEGORICAL + descriptor_cols), TextEvals(columns=descriptor_cols)]
    if ref_ds is not None:
        # Only compare signals present in both runs (e.g. the original pipeline has no reranker -> rerank_ms empty).
        shared_numeric = [c for c in numeric_cols if ref[c].notna().any()]
        drift_cols = shared_numeric + CATEGORICAL + descriptor_cols + (["question", "answer"] if len(cur) >= 20 else [])
        metrics.append(DataDriftPreset(columns=drift_cols))
    snapshot = Report(metrics, metadata={"run": run_name, "reference": str(ref_path) if ref_path else ""}).run(
        current_data=cur_ds, reference_data=ref_ds, name=f"Vellum RAG {run_name}")
    snapshot.save_html(str(out_dir / "report.html"))
    snapshot.save_json(str(out_dir / "report.json"))

    # Track over time: local workspace (Evidently UI dashboards) + flat CSV history.
    try:
        from evidently.ui.workspace import Workspace
        ws = Workspace.create(str(REPORTS_DIR / "evidently_workspace"))
        projects = [p for p in ws.search_project("Vellum RAG")] if hasattr(ws, "search_project") else []
        project = projects[0] if projects else ws.create_project("Vellum RAG")
        ws.add_run(project.id, snapshot, include_data=False)
        ws_status = "added"
    except Exception as e:
        ws_status = f"skipped ({type(e).__name__}: {str(e)[:120]})"

    summary = {
        "run": run_name, "timestamp": datetime.datetime.now().isoformat(timespec="seconds"), "rows": len(cur),
        "reference": str(ref_path) if ref_path else None,
        "refusal_rate": round((cur["is_refusal"] == "True").mean(), 3),
        "citation_rate_non_refusal": round(cur.loc[cur["is_refusal"] != "True", "answer"].str.contains(r"\[\d+\]").mean(), 3)
        if (cur["is_refusal"] != "True").any() else None,
        "no_citation_warnings": int((cur["grounding_warning"] == "no_citations").sum()),
        **{f"{c}_p50": (round(float(cur[c].median()), 1) if cur[c].notna().any() else None)
           for c in ("total_ms", "retrieval_ms", "rerank_ms", "generation_ms", "ttft_ms", "prompt_tokens")},
        **{f"{c}_mean": (round(float(cur[c].mean()), 3) if cur[c].notna().any() else None)
           for c in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")},
        "workspace": ws_status,
    }
    hist = REPORTS_DIR / "evidently_history.csv"
    new = not hist.exists()
    with open(hist, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()), extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(summary)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("saved", out_dir / "report.html")


if __name__ == "__main__":
    main()
