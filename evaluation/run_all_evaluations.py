"""Run the complete evaluation suite and write a consolidated summary.

Steps (each in its own process, since TruLens and the pipeline exporter both configure OpenTelemetry):
  1. collect   - run every dataset question through the real pipeline (traced to Phoenix if it is running)
  2. ragas     - Ragas metrics on the collected records
  3. deepeval  - DeepEval metrics + thresholds + judge calibration
  4. trulens   - TruLens RAG triad on the live pipeline
  5. evidently - Evidently data-quality / text / drift report + history
  6. phoenix   - trace completeness, stage latency, privacy scan, score annotations
  7. summary   - consolidated JSON + Markdown in the run directory

    python evaluation/run_all_evaluations.py [--limit N] [--run-name NAME] [--skip trulens,deepeval] [--records PATH]

Prerequisites: .venv-eval (see evaluation/requirements-eval.txt), GROQ_API_KEY, a local eval database
(scripts/local_postgres.py) and optionally Phoenix (python -m phoenix.server.main serve).
"""
import argparse
import datetime
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.evaluation_config import RUNS_DIR, THRESHOLDS  # noqa: E402

PY = sys.executable


def run(step, args):
    print(f"\n=== {step} ===", flush=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    rc = subprocess.call([PY, *args], cwd=ROOT, env=env)
    print(f"=== {step} exit code {rc} ===", flush=True)
    return rc


def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def behaviour(records):
    neg = [r for r in records if r["category"] in ("unanswerable", "out_of_domain")]
    pos = [r for r in records if r["category"] in ("answerable", "multi_doc")]
    refused = lambda r: bool((r.get("meta") or {}).get("validation", {}).get("is_refusal"))
    lat = [r["meta"]["timings_ms"]["total_ms"] for r in records if (r.get("meta") or {}).get("timings_ms", {}).get("total_ms")]
    gen = [r["meta"]["timings_ms"]["generation_ms"] for r in records if (r.get("meta") or {}).get("timings_ms", {}).get("generation_ms")]
    ret = [r["meta"]["timings_ms"]["retrieval_ms"] for r in records if (r.get("meta") or {}).get("timings_ms", {}).get("retrieval_ms")]
    toks = [(r["meta"].get("usage") or {}).get("prompt_tokens", 0) + (r["meta"].get("usage") or {}).get("completion_tokens", 0)
            for r in records if r.get("meta")]
    cited = [r for r in pos if not refused(r)]
    return {
        "refusal_rate_unanswerable": round(sum(map(refused, neg)) / len(neg), 3) if neg else None,
        "false_refusal_rate_answerable": round(sum(map(refused, pos)) / len(pos), 3) if pos else None,
        "citation_rate_answered": round(sum(1 for r in cited if (r["meta"].get("validation") or {}).get("cited_refs")) / len(cited), 3) if cited else None,
        "pipeline_errors": sum(1 for r in records if r.get("error")),
        "latency_ms": {"total_p50": round(statistics.median(lat), 1) if lat else None,
                       "total_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1) if lat else None,
                       "retrieval_p50": round(statistics.median(ret), 1) if ret else None,
                       "generation_p50": round(statistics.median(gen), 1) if gen else None},
        "tokens": {"total": sum(toks), "per_question_mean": round(statistics.mean(toks), 1) if toks else None},
    }


def write_summary(run_dir: Path):
    from evaluation.common import read_records  # noqa: WPS433 (imports backend env)
    records = read_records(run_dir / "records.jsonl")
    ragas, deep = load(run_dir / "ragas" / "ragas_results.json"), load(run_dir / "deepeval" / "deepeval_results.json")
    tru, evid = load(run_dir / "trulens" / "trulens_results.json"), load(run_dir / "evidently" / "summary.json")
    phx = load(run_dir / "phoenix_summary.json")
    beh = behaviour(records)
    summary = {
        "run": run_dir.name, "generated": datetime.datetime.now().isoformat(timespec="seconds"), "samples": len(records),
        "behaviour": beh, "thresholds": THRESHOLDS,
        "ragas": ragas and {"judge": ragas["judge_model"], **{k: v for k, v in ragas["summary"].items() if not k.startswith("_")}},
        "deepeval": deep and {"judge": deep["judge_model"], "calibration": deep["calibration"], "summary": deep["summary"],
                              "failed_cases": len(deep["failed_cases"])},
        "trulens": tru and {"judge": tru["judge_model"], "summary": tru["summary"]},
        "evidently": evid,
        "phoenix": phx and {k: phx[k] for k in ("phoenix_url", "project", "complete_traces", "traced_records",
                                                  "secret_leaks", "annotations_logged", "llm_tokens", "stage_latency")},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    def fmt(x):
        return "n/a" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
    lines = [f"# Evaluation summary: {run_dir.name}", "", f"Samples: {len(records)}", "",
             "Scores from different frameworks use different judges and definitions; compare each only with its own threshold.", "",
             "| Framework | Metric | Score | Threshold | n |", "|---|---|---|---|---|"]
    if ragas:
        for k, v in ragas["summary"].items():
            if not k.startswith("_"):
                lines.append(f"| Ragas ({ragas['judge_model']}) | {k} | {fmt(v['mean'])} | {fmt(v.get('threshold'))} | {v['n']} |")
    if deep:
        for k, v in deep["summary"].items():
            lines.append(f"| DeepEval ({deep['judge_model']}) | {k} | {fmt(v['mean'])} (pass {fmt(v['pass_rate'])}) | "
                         f"{fmt(THRESHOLDS['deepeval'].get(k, THRESHOLDS['deepeval'].get('hallucination_min')))} | {v['n']} |")
    if tru:
        for k, v in tru["summary"].items():
            lines.append(f"| TruLens ({tru['judge_model']}) | {k} | {fmt(v['mean'])} | {fmt(v.get('threshold'))} | {v['n']} |")
    lines += ["", "## Behaviour and latency (no LLM judge)", "", "```json", json.dumps(beh, indent=1), "```"]
    if phx:
        lines += ["", f"Phoenix: {phx['complete_traces']}/{phx['traced_records']} complete traces, "
                      f"{len(phx['secret_leaks'])} secret findings, {phx['annotations_logged']} score annotations ({phx['phoenix_url']})."]
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--run-name", default=datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--records", help="reuse existing records instead of collecting")
    ap.add_argument("--skip", default="", help="comma list: collect,ragas,deepeval,trulens,evidently,phoenix")
    ap.add_argument("--parallel", action="store_true",
                    help="run Ragas, DeepEval and TruLens concurrently (they use different judge models, so different "
                         "per-model rate-limit budgets)")
    ap.add_argument("--reference", help="records.jsonl of a reference run for Evidently drift")
    ap.add_argument("--ids", help="comma-separated sample ids for the LLM-judged frameworks (rate-limit budget)")
    a = ap.parse_args()
    skip = set(filter(None, a.skip.split(",")))
    if a.records:
        records = Path(a.records)
    else:
        records = RUNS_DIR / a.run_name / "records.jsonl"
        if "collect" not in skip:
            extra = ["--limit", str(a.limit)] if a.limit else []
            if run("collect", ["-m", "evaluation.common", "--run-name", a.run_name, *extra]) != 0:
                sys.exit("collection failed")
    rec = ["--records", str(records)]
    lim = ["--limit", str(a.limit)] if a.limit else []
    ids = ["--ids", a.ids] if a.ids else []
    results = {}
    judged = [(s, args) for s, args in (("ragas", ["evaluation/ragas_evaluation.py", *rec, *ids]),
                                        ("deepeval", ["evaluation/deepeval_evaluation.py", *rec, *ids]),
                                        ("trulens", ["evaluation/trulens_evaluation.py", *rec, *lim, *ids])) if s not in skip]
    if a.parallel:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        logs = {s: open(records.parent / f"{s}.log", "w", encoding="utf-8") for s, _ in judged}
        procs = {s: subprocess.Popen([PY, *args], cwd=ROOT, env=env, stdout=logs[s], stderr=subprocess.STDOUT)
                 for s, args in judged}
        print("running in parallel:", ", ".join(procs), "(logs in", records.parent, ")", flush=True)
        for s, p in procs.items():
            results[s] = p.wait()
            logs[s].close()
            print(f"=== {s} exit code {results[s]} ===", flush=True)
    else:
        for s, args in judged:
            results[s] = run(s, args)
    ref = ["--reference", a.reference] if a.reference else []
    for step, args in (("evidently", ["evaluation/evidently_monitoring.py", *rec, *ref]),
                       ("phoenix", ["evaluation/phoenix_tracing.py", *rec])):
        if step not in skip:
            results[step] = run(step, args)
    write_summary(records.parent)
    print("\nstep exit codes:", results)


if __name__ == "__main__":
    main()
