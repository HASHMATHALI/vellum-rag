"""Performance measurements for PERFORMANCE_REPORT.md (run on an otherwise idle machine).

Component benchmarks run in-process against the local embedded Postgres ('rag_perf' database):
  - ingestion (parse + chunk + embed + insert) per corpus file
  - embedding latency (single query, batch of 32)
  - vector search latency on a synthetic multi-tenant corpus (N chunks, 50 users): exact scan vs HNSW,
    and recall@10 of HNSW (with iterative scan) vs exact for a per-user filter
  - reranker latency vs number of candidates
  - event-loop responsiveness while a document is being indexed
End-to-end (HTTP, --base): /api/query latency for answerable (LLM) and refused (no LLM) questions, and
concurrent requests on the non-LLM path. Process memory/CPU are sampled with psutil (--server-pid).

    python scripts/perf_benchmark.py [--chunks 20000] [--base http://127.0.0.1:8000] [--server-pid PID]
"""
import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pct(vals, p):
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))], 2)


def stats(vals):
    return {"p50": pct(vals, 50), "p95": pct(vals, 95), "mean": round(statistics.mean(vals), 2), "n": len(vals)}


def db_url(name):
    out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "local_postgres.py"), name], text=True,
                                  stderr=subprocess.DEVNULL)
    return [l for l in out.splitlines() if l.startswith(name + "=")][0].split("=", 1)[1]


os.environ.update({"DATABASE_URL": db_url("rag_perf"), "ENVIRONMENT": "test", "LOG_FILE": "", "SUPABASE_URL": "",
                   "SUPABASE_KEY": "", "GROQ_API_KEY": "", "REDIS_URL": ""})
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
from sqlalchemy import delete, text  # noqa: E402

from app.database.connection import async_session, engine, system_session  # noqa: E402
from app.database.migrations import run_migrations  # noqa: E402
from app.embeddings.embedder import embedder  # noqa: E402
from app.models.document import Document, DocumentChunk  # noqa: E402
from app.models.user import User  # noqa: E402
from app.retrieval.reranker import reranker  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402

CORPUS = ROOT / "evaluation" / "datasets" / "corpus"


async def bench_ingestion(user_id):
    res = {}
    async with system_session() as db:
        for f in sorted(CORPUS.iterdir()):
            data = f.read_bytes()
            doc = Document(filename=f.name, filepath="perf", file_type=f.suffix.strip("."), file_size=len(data),
                           user_id=user_id, status="processing")
            db.add(doc)
            await db.commit()
            t0 = time.perf_counter()
            n = await DocumentService.index_bytes(db, doc, data)
            res[f.name] = {"bytes": len(data), "chunks": n, "ms": round((time.perf_counter() - t0) * 1000, 1)}
    return res


def bench_embedding():
    embedder.get_embeddings(["warm"])
    single = []
    for i in range(30):
        t0 = time.perf_counter(); embedder.get_embeddings([f"what is the chunk size question {i}"]); single.append((time.perf_counter() - t0) * 1000)
    texts = ["Vellum stores embeddings in pgvector. " * 25] * 32
    batch = []
    for _ in range(5):
        t0 = time.perf_counter(); embedder.get_embeddings(texts); batch.append((time.perf_counter() - t0) * 1000)
    return {"single_query_ms": stats(single), "batch32_1000chars_ms": stats(batch),
            "per_chunk_ms_in_batch": round(statistics.median(batch) / 32, 2)}


def bench_rerank():
    reranker.score("warm", ["warm"])
    out = {}
    passage = "Vellum stores embeddings in pgvector and uses HNSW indexes for search. " * 14  # ~1000 chars
    for n in (5, 10, 15, 20):
        vals = []
        for _ in range(5):
            t0 = time.perf_counter(); reranker.score("how are vectors indexed?", [passage] * n); vals.append((time.perf_counter() - t0) * 1000)
        out[f"{n}_candidates_ms"] = stats(vals)
    return out


async def bench_vector_search(n_chunks, n_users=50, big_tenant=10000):
    """Synthetic multi-tenant corpus: n_users small tenants sharing n_chunks, plus one large tenant."""
    rng = np.random.default_rng(0)
    async with system_session() as db:
        users = [User(email=f"perf-{i}@x.local", hashed_password="!", role="user") for i in range(n_users + 1)]
        db.add_all(users)
        await db.flush()
        docs = [Document(filename="synthetic", filepath="perf", file_type="txt", file_size=1, user_id=u.id, status="indexed")
                for u in users]
        db.add_all(docs)
        await db.flush()
        total = n_chunks + big_tenant
        vecs = rng.normal(size=(total, 384)).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        for i in range(total):
            d = docs[i % n_users] if i < n_chunks else docs[-1]
            db.add(DocumentChunk(document_id=d.id, user_id=d.user_id, chunk_index=i, text_content=f"synthetic chunk {i}",
                                 page_number=1, embedding=vecs[i].tolist()))
            if i % 2000 == 1999:
                await db.flush()
        await db.commit()
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE document_chunks"))
        ver = (await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))).scalar()
    queries = rng.normal(size=(30, 384)).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    sql_index = text("SELECT id FROM document_chunks WHERE user_id = :u ORDER BY embedding <=> CAST(:q AS vector) LIMIT 10")
    sql_exact = text("SELECT id FROM document_chunks WHERE user_id = :u ORDER BY (embedding <=> CAST(:q AS vector)) + 0 LIMIT 10")
    major, minor = (int(x) for x in ver.split(".")[:2])
    res = {"pgvector": ver, "corpus": {"small_tenants": n_users, "chunks_per_small_tenant": n_chunks // n_users,
                                       "large_tenant_chunks": big_tenant, "total_chunks": n_chunks + big_tenant}}
    for label, uid in (("small_tenant", users[7].id), ("large_tenant", users[-1].id)):
        exact_ids, entry = [], {}
        modes = [("exact_per_tenant", sql_exact, []), ("hnsw_plain_ef40", sql_index, [])]
        if (major, minor) >= (0, 8):
            modes.append(("hnsw_iterative_ef100", sql_index, ["SET LOCAL hnsw.ef_search = 100",
                                                            "SET LOCAL hnsw.iterative_scan = 'relaxed_order'"]))
        for mode, sql, sets in modes:
            lat, ids = [], []
            for q in queries:
                async with async_session() as db:
                    for st in sets:
                        await db.execute(text(st))
                    t0 = time.perf_counter()
                    rows = (await db.execute(sql, {"u": uid, "q": str(q.tolist())})).scalars().all()
                    lat.append((time.perf_counter() - t0) * 1000)
                    ids.append(set(rows))
            if mode == "exact_per_tenant":
                exact_ids = ids
            entry[mode] = {"latency_ms": stats(lat), "avg_rows_returned_of_10": round(statistics.mean(len(x) for x in ids), 2),
                           "recall@10_vs_exact": round(statistics.mean(len(a & b) / 10 for a, b in zip(ids, exact_ids)), 3)}
        async with async_session() as db:
            entry["plan_exact"] = (await db.execute(text("EXPLAIN " + sql_exact.text), {"u": uid, "q": str(queries[0].tolist())})).scalars().all()
        res[label] = entry
    return res


async def bench_event_loop(user_id):
    """Health-check-like coroutine latency while a large document is indexed concurrently."""
    big = (CORPUS / "vellum_masterclass.pdf").read_bytes()
    async with system_session() as db:
        doc = Document(filename="loop.pdf", filepath="perf", file_type="pdf", file_size=len(big), user_id=user_id, status="processing")
        db.add(doc)
        await db.commit()
        lat = []
        done = asyncio.Event()

        async def ticker():
            while not done.is_set():
                t0 = time.perf_counter()
                await asyncio.sleep(0.01)
                lat.append((time.perf_counter() - t0) * 1000 - 10)

        t = asyncio.create_task(ticker())
        await DocumentService.index_bytes(db, doc, big)
        done.set()
        await t
    return {"scheduler_delay_ms_during_indexing": stats(lat), "max_ms": round(max(lat), 1)}


async def bench_http(base, server_pid, with_llm=True):
    import httpx
    import psutil
    out = {}
    proc = psutil.Process(server_pid) if server_pid else None
    async with httpx.AsyncClient(base_url=base, timeout=120) as c:
        s = (await c.post("/api/auth/guest")).json()
        h = {"Authorization": f"Bearer {s['access_token']}"}
        r = await c.post("/api/upload", headers=h, files={"file": ("guide.pdf", (CORPUS / "vellum_masterclass.pdf").read_bytes(), "application/pdf")})
        await asyncio.sleep(8)

        async def ask(q):
            t0 = time.perf_counter()
            body = (await c.post("/api/query", headers=h, json={"message": q})).text
            total = (time.perf_counter() - t0) * 1000
            meta = {}
            for line in body.splitlines():
                if line.startswith("data:") and '"timings_ms"' in line:
                    meta = json.loads(line[5:])
            return total, meta

        answered, refused, ttft, prompt_tok, gen = [], [], [], [], []
        for q in ([] if not with_llm else ["Why did the project migrate from FAISS to pgvector?", "What is HyDE?", "How does MMR work?",
                  "What is the difference between IVFFlat and HNSW?", "How is SSE buffering handled in Nginx?"]):
            total, meta = await ask(q)
            answered.append(total)
            if meta.get("ttft_ms"):
                ttft.append(meta["ttft_ms"])
            gen.append(meta.get("timings_ms", {}).get("generation_ms", 0))
            prompt_tok.append(meta.get("usage", {}).get("prompt_tokens", 0))
            await asyncio.sleep(4)  # stay under Groq's per-minute token budget
        for q in ["What is the capital of Australia?", "Who won the 2018 World Cup?", "Best pizza topping?"]:
            refused.append((await ask(q))[0])
        if answered:
            out["e2e_answered_ms"] = stats(answered)
            out["ttft_ms"] = stats(ttft) if ttft else None
            out["generation_ms"] = stats(gen)
            out["prompt_tokens"] = stats(prompt_tok)
        out["e2e_refused_no_llm_ms"] = stats(refused)

        cpu0 = proc.cpu_times() if proc else None
        t0 = time.perf_counter()
        conc = 10
        res = await asyncio.gather(*[ask("Who won the 2018 World Cup?") for _ in range(conc)])
        wall = time.perf_counter() - t0
        out["concurrent_no_llm"] = {"requests": conc, "wall_s": round(wall, 2), "throughput_rps": round(conc / wall, 2),
                                    "latency_ms": stats([r[0] for r in res])}
        t0 = time.perf_counter()
        hl = await asyncio.gather(*[c.get("/api/health/live") for _ in range(200)])
        wall = time.perf_counter() - t0
        out["health_throughput_rps"] = round(len(hl) / wall, 1)
        if proc:
            cpu1 = proc.cpu_times()
            out["server_process"] = {"rss_mb": round(proc.memory_info().rss / 1e6, 1),
                                     "cpu_seconds_during_concurrency_tests": round((cpu1.user + cpu1.system) - (cpu0.user + cpu0.system), 2)}
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=int, default=20000)
    ap.add_argument("--base")
    ap.add_argument("--server-pid", type=int)
    ap.add_argument("--no-llm", action="store_true", help="skip HTTP queries that call the LLM (rate-limit budget)")
    ap.add_argument("--http-only", action="store_true", help="only run the HTTP benchmark and merge into the results file")
    a = ap.parse_args()
    out = ROOT / "reports" / "performance" / "perf_results.json"
    if a.http_only:
        report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        report["http"] = await bench_http(a.base, a.server_pid, with_llm=not a.no_llm)
        out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        print(json.dumps(report["http"], indent=1))
        return
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await run_migrations(engine)
    async with system_session() as db:
        u = User(email="perf-owner@x.local", hashed_password="!", role="user")
        db.add(u)
        await db.commit()
        uid = u.id
    report = {"machine": {"cpu": os.cpu_count()}, "embedding": bench_embedding(), "rerank": bench_rerank()}
    report["ingestion"] = await bench_ingestion(uid)
    report["event_loop"] = await bench_event_loop(uid)
    report["vector_search"] = await bench_vector_search(a.chunks)
    if a.base:
        report["http"] = await bench_http(a.base, a.server_pid, with_llm=not a.no_llm)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, indent=1, default=str)[:5000])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
