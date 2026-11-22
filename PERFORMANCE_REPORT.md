# Performance Report: Vellum RAG

**Date:** 2026-11-22
**Hardware:** laptop, Intel i7-1355U (10 cores / 12 threads, power-managed U-series), 16 GB RAM, no GPU, Windows 11.
**Database:** local PostgreSQL 16.2 with pgvector **0.6.2** (embedded `pgserver`). Supabase runs pgvector 0.8.
**LLM:** Groq `openai/gpt-oss-120b`.

Raw data:
- `reports/performance/perf_results.json`, `perf_results_rerank_on.json`, `perf_results_rerank_off.json`, `original_event_loop.json`
- `evaluation/reports/retrieval_original.json`, `retrieval_current*.json`, `retrieval_rerank_top{10,15}.json`

Scripts: `scripts/perf_benchmark.py`, `evaluation/retrieval_benchmark.py`.

> **Caveats.**
> - The LLM-judged evaluation jobs were running on the same laptop during the HTTP concurrency tests. CPU-bound numbers there are pessimistic.
> - Groq's free-tier limits (8K tokens/min, **200K tokens/day per model**) dominated what could be measured end to end. The HTTP benchmark therefore excludes LLM calls; generation latency comes from the real evaluation records.

## 1. Before → after summary

| Measure | Original (20c2aef) | Improved | Notes |
|---|---|---|---|
| LLM answers | **0%**: model retired (HTTP 404) | 100% of non-refused questions answered | Configurable model + fallback |
| Event-loop stall while indexing a 14-page PDF | **max 2,152 ms** (embedding ran on the loop) | **max 28 ms**, p95 22 ms | Parse/embed/rerank in a threadpool |
| Retrieval quality (hit@5 / MRR@5) | semantic 0.905 / 0.770 | hybrid + rerank **0.952 / 0.873** | 21 answerable questions with evidence labels |
| Context precision proxy (P@5, before threshold) | 0.267 | 0.324 | Threshold and margin then drop low-scoring chunks |
| Contexts sent to the LLM (avg) | 5.0 | 2.7 | Smaller prompts, fewer distractors |
| Answer length (avg chars) | 2,556 | 531 | Concise, cited answers |
| Off-topic question cost | LLM always called | **no LLM call** (reranker threshold) | Measured: with the reranker off, 15 off-topic requests reached the LLM |
| Retrieval latency, no rerank (p50) | 14 ms | 7–10 ms (hybrid) | Batched lookups (N+1 query removed) |
| Retrieval latency with rerank (p50) | n/a | ~1.1 s (10 candidates) | Price of the quality gain on CPU (§3) |
| Ingestion: masterclass PDF | 1.2 s (25 chunks) | 3.6 s (24 chunks) | Slower: 4-thread torch cap, section-aware embedding text, injection scoring (§2) |
| Concurrent no-LLM queries (10 parallel) | n/a | 0.79 req/s, p50 7.3 s | CPU-bound on the cross-encoder (§4) |

## 2. Components (`perf_results.json`)

| Component | p50 | p95 | Notes |
|---|---|---|---|
| Query embedding (MiniLM, 1 sentence) | 13.3 ms | 14.7 ms | LRU cache makes repeated queries ~0 ms |
| Batch embedding: 32 chunks × 1,000 chars | 1,473 ms | 1,495 ms | 46 ms per chunk with `TORCH_THREADS=4` |
| Rerank 5 / 10 / 15 / 20 candidates | 331 / 558 / 862 / 1,168 ms | | ~55 ms per pair, linear |
| Ingestion (parse + chunk + embed + insert) | md 2–3 KB: 0.2–0.6 s; docx 39 KB: 0.94 s; csv: 0.13 s; pdf 394 KB: 3.63 s | | Background task: upload returns 201 immediately |

**Decision: `RERANK_TOP_N` 15 → 10.** Quality was identical on the benchmark (hit@5 0.952, MRR 0.873, P@5 0.324 for both), and p50 retrieval latency fell from 1.63 s to 1.10 s.

**Ingestion trade-off.** Capping torch to 4 threads per call slows a single large ingestion (about 3× versus the original, which used all cores). In exchange, concurrent requests stop thrashing the CPU (§4). On a dedicated worker, raise `TORCH_THREADS`.

## 3. Vector search: correctness under multi-tenancy (important)

The synthetic corpus has 50 tenants × 400 chunks plus one tenant with 10,000 chunks (30,000 vectors, 384-d), and 30 queries per scenario.

| Tenant | Method | p50 | Rows returned of 10 | Recall@10 vs exact |
|---|---|---|---|---|
| Small (400 chunks) | **exact per-tenant (default)** | **2.3 ms** | **10** | **1.00** |
| Small | HNSW, user filter (pgvector 0.6, ef_search 40) | 3.3 ms | **0.83** | 0.08 |
| Large (10,000 chunks) | **exact per-tenant** | **6.6 ms** | 10 | 1.00 |
| Large | HNSW, user filter | 3.4 ms | 8.9 | 0.09 |

**Finding.** An HNSW index combined with a `WHERE user_id = …` filter post-filters the index's candidate list. On pgvector < 0.8 this silently returns almost nothing for small tenants. My first migration added an HNSW index, so this would have been a severe regression. The retriever therefore defaults to **exact search within the tenant's rows** (`VECTOR_SEARCH=exact`, located through the `user_id` index), which costs single-digit milliseconds at these sizes. `VECTOR_SEARCH=hnsw` turns on HNSW with iterative scans (`hnsw.iterative_scan = relaxed_order`, ef_search 100) **only on pgvector ≥ 0.8**; otherwise it falls back to exact search and logs a warning.

Iterative-scan recall could not be measured locally (pgvector 0.6.2). The low HNSW recall on *random* vectors partly reflects synthetic data; real embeddings cluster and index better. Exact search stays correct regardless.

## 4. End-to-end HTTP (`perf_results*.json` → `http`)

| Scenario | Reranker on (default) | Reranker off |
|---|---|---|
| Single off-topic query, refused (p50) | 1.03 s (0 LLM calls) | 0.63 s, **but off-topic questions then reach the LLM** |
| 10 concurrent off-topic queries | 12.6 s wall, **0.79 req/s**, p50 7.3 s | 59 s wall: 15 LLM calls hit the exhausted Groq budget (not a valid throughput figure; it shows why the threshold matters) |
| `/api/health/live` throughput | 508 req/s | 299 req/s |
| Backend RSS | 853 MB | 663 MB |

Effect of the concurrency fixes (`TORCH_THREADS=4`, `MODEL_CONCURRENCY=2` semaphore, `RERANK_TOP_N=10`), same 10-request load: **0.55 → 0.79 req/s (+44%)**, p50 latency **17.2 s → 7.3 s**, health throughput **210 → 508 req/s**.

**LLM stage** (from the evaluation run; laptop busy, 120b model):

| | p50 | Source |
|---|---|---|
| Time to first token | ~0.7 s | `ttft_ms` in records |
| Generation (stream complete) | 0.7–1.3 s | `generation_ms` |
| Prompt tokens per answered question | ~1,100–1,500 | `usage` |
| Whole request, answered (laptop under load) | 1.5–13 s | dominated by reranking under contention |

## 5. Optimisations implemented

- Threadpool for all CPU work (parse, embed, rerank), so the event loop no longer blocks (measured above).
- Model warm-up at startup in the background, removing the ~25 s first-request penalty seen before warm-up.
- Query-embedding LRU cache, batch embedding (`EMBEDDING_BATCH_SIZE=32`) and normalised vectors.
- Exact per-tenant vector search (correct and fast), full-text GIN index, and RRF fusion.
- Rerank top-10, a bounded model-concurrency semaphore and capped torch threads.
- No LLM call when nothing relevant is retrieved; prompt history capped at 6 messages; context budget of 3,000 tokens with deduplication.
- N+1 document lookups removed (filename joined in the retrieval query).
- DB pool tuned (`pool_size=10`, overflow 10, recycle 30 min, pre-ping), Postgres `statement_timeout` 30 s, LLM timeouts and retries.
- Gunicorn with N uvicorn workers in the container; nginx gzip and immutable asset caching.

## 6. Scaling guidance

- **Throughput is bounded by the CPU cross-encoder: about 0.8–1 req/s per 4-core worker.** Options: more workers/CPUs; a GPU; disable reranking for latency-critical tenants (`RERANKER_ENABLED=false`, lower quality, and off-topic filtering falls back to cosine); or a hosted reranker.
- **LLM capacity on the current Groq free tier:** 200K tokens/day per model is roughly **130 answers/day** on the primary model before the fallback takes over. Move to Groq Dev tier for production.
- Use **Redis** for shared rate limits once there is more than one worker.
- For tenants above ~100K chunks, use pgvector ≥ 0.8 with `VECTOR_SEARCH=hnsw`.
