"""TruLens RAG Triad (context relevance, groundedness, answer relevance) on the *live* pipeline.

The real Vellum pipeline is wrapped in an instrumented app: `retrieve()` (RETRIEVAL span with the query and
retrieved contexts) and `generate()` (GENERATION span), called from `query()` (record root). TruLens records each
call through OpenTelemetry and evaluates feedback functions on the recorded spans. Records and feedback are stored
in a local SQLite DB (evaluation/reports/runs/<run>/trulens/trulens.sqlite).

Judge: Groq through TruLens' OpenAI provider (EVAL_TRULENS_MODEL, default openai/gpt-oss-120b).

    python evaluation/trulens_evaluation.py [--records ...] [--limit N]
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("TRULENS_OTEL_TRACING", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.evaluation_config import GROQ_BASE_URL, THRESHOLDS, configure_backend_env, groq_api_key  # noqa: E402

configure_backend_env()

import numpy as np  # noqa: E402
from trulens.apps.app import TruApp  # noqa: E402
from trulens.core import Feedback, TruSession  # noqa: E402
from trulens.core.feedback.selector import Selector  # noqa: E402
from trulens.core.otel.instrument import instrument  # noqa: E402
from trulens.otel.semconv.trace import SpanAttributes  # noqa: E402
from trulens.providers.openai import OpenAI as TruOpenAI  # noqa: E402

from app.database.connection import async_session  # noqa: E402
from app.rag.pipeline import pipeline, normalize_citations  # noqa: E402
from evaluation.common import ingest_corpus, load_dataset  # noqa: E402
from evaluation.ragas_evaluation import latest_records  # noqa: E402

MODEL = os.environ.get("EVAL_TRULENS_MODEL", "openai/gpt-oss-120b")


class VellumRAG:
    """Thin synchronous facade over the async production pipeline, instrumented for TruLens."""

    def __init__(self, user_id: int, loop):
        self.user_id = user_id
        self.loop = loop  # same loop as the DB pool (asyncpg connections are loop-bound)
        self._prepared = None

    async def _prepare(self, question: str):
        async with async_session() as db:
            return await pipeline.prepare(db, self.user_id, question, mode="hybrid", k=5)

    @instrument(span_type=SpanAttributes.SpanType.RETRIEVAL,
                attributes={SpanAttributes.RETRIEVAL.QUERY_TEXT: "query",
                            SpanAttributes.RETRIEVAL.RETRIEVED_CONTEXTS: "return"})
    def retrieve(self, query: str) -> list:
        self._prepared = self.loop.run_until_complete(self._prepare(query))
        return [c.text for c in self._prepared.context.chunks]

    @instrument(span_type=SpanAttributes.SpanType.GENERATION)
    def generate(self, query: str, contexts: list) -> str:
        meta: dict = {}

        async def run():
            return "".join([t async for t in pipeline.stream(self._prepared, meta)])
        return normalize_citations(self.loop.run_until_complete(run()))

    @instrument()  # becomes the record root because it is TruApp's main_method
    def query(self, query: str) -> str:
        contexts = self.retrieve(query)
        return self.generate(query, contexts)


def feedbacks(provider):
    f_context = (Feedback(provider.context_relevance_with_cot_reasons, name="Context Relevance")
                 .on({"question": Selector.select_record_input(), "context": Selector.select_context(collect_list=False)})
                 .aggregate(np.mean))
    f_ground = (Feedback(provider.groundedness_measure_with_cot_reasons, name="Groundedness")
                .on({"source": Selector.select_context(collect_list=True), "statement": Selector.select_record_output()}))
    f_answer = (Feedback(provider.relevance_with_cot_reasons, name="Answer Relevance")
                .on({"prompt": Selector.select_record_input(), "response": Selector.select_record_output()}))
    return [f_context, f_ground, f_answer]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", help="run whose directory receives the TruLens report (questions come from the dataset)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", help="comma-separated sample ids")
    args = ap.parse_args()
    run_dir = (Path(args.records) if args.records else latest_records()).parent
    out_dir = run_dir / "trulens"
    out_dir.mkdir(exist_ok=True)
    db_path = out_dir / "trulens.sqlite"
    if db_path.exists():
        db_path.unlink()
    os.environ["GROQ_API_KEY"] = groq_api_key()

    session = TruSession(database_url=f"sqlite:///{db_path.as_posix()}")
    # OpenAI-compatible provider pointed at Groq (TruLens' LiteLLM provider rejects models missing from its cost map).
    provider = TruOpenAI(model_engine=MODEL, base_url=GROQ_BASE_URL, api_key=groq_api_key(), rpm=20)
    loop = asyncio.new_event_loop()
    user, _ = loop.run_until_complete(ingest_corpus())
    app = VellumRAG(user.id, loop)
    tru_app = TruApp(app, app_name="VellumRAG", app_version="v2-hybrid-rerank", feedbacks=feedbacks(provider),
                     main_method=app.query, start_evaluator=False)
    samples = [s for s in load_dataset(args.limit)]
    if args.ids:
        keep = set(args.ids.split(","))
        samples = [s for s in samples if s["id"] in keep]
    t0 = time.time()
    for s in samples:
        with tru_app as recording:
            recording.record_metadata = {"id": s["id"], "category": s["category"]}
            ans = app.query(s["question"])
        print(f"[trulens] recorded {s['id']}: {ans[:80]!r}")
        time.sleep(2)
    session.force_flush()
    print("[trulens] computing feedback ...")
    tru_app.compute_feedbacks(raise_error_on_no_feedbacks_computed=False)
    session.force_flush()

    records, fb_cols = session.get_records_and_feedback(app_ids=[tru_app.app_id])
    leaderboard = session.get_leaderboard(app_ids=[tru_app.app_id])
    rows = []
    for _, r in records.iterrows():
        inp = r.get("input")
        sample = next((s for s in samples if s["question"] in str(inp)), None)
        rows.append({"id": sample["id"] if sample else None, "category": sample["category"] if sample else None,
                     "input": str(inp)[:200], "output": str(r.get("output"))[:500],
                     **{c: (None if r.get(c) is None or (isinstance(r.get(c), float) and np.isnan(r.get(c))) else round(float(r.get(c)), 4))
                        for c in fb_cols}, "latency_s": r.get("latency")})
    th = THRESHOLDS["trulens"]
    key = {"Context Relevance": "context_relevance", "Groundedness": "groundedness", "Answer Relevance": "answer_relevance"}
    summary = {}
    for col in fb_cols:
        vals = [x[col] for x in rows if x.get(col) is not None]
        name = key.get(col, col)
        summary[name] = {"mean": round(statistics.mean(vals), 4) if vals else None, "n": len(vals), "threshold": th.get(name)}
        if vals and th.get(name) is not None:
            summary[name]["pass"] = summary[name]["mean"] >= th[name]
    from app.config.settings import settings as app_settings
    report = {"framework": "trulens", "sample_ids": [s["id"] for s in samples], "generation_model": app_settings.LLM_MODEL, "version": __import__("importlib.metadata").metadata.version("trulens-core"),
              "judge_model": MODEL, "app": "VellumRAG/v2-hybrid-rerank", "seconds": round(time.time() - t0, 1),
              "sqlite": str(db_path), "summary": summary,
              "leaderboard": json.loads(leaderboard.reset_index().to_json(orient="records", default_handler=str)),
              "per_record": rows}
    (out_dir / "trulens_results.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("saved", out_dir / "trulens_results.json")


if __name__ == "__main__":
    main()
