"""Retrieval engine: semantic (pgvector HNSW), hybrid (vector + Postgres full-text, fused with RRF) and MMR,
followed by optional cross-encoder reranking and a relevance threshold.

Authorisation is part of the query itself: every SQL statement is restricted to chunks whose owner is
`user_id` and whose document is fully indexed. The caller cannot omit the filter.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.embeddings.embedder import embedder
from app.models.document import Document, DocumentChunk
from app.retrieval.reranker import reranker

logger = logging.getLogger(__name__)
RRF_K = 60
_TOKEN = re.compile(r"[A-Za-z0-9]{2,}")


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    page_number: int
    section: Optional[str]
    text: str
    score: float  # final ranking score (rerank logit, RRF or cosine)
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    rerank_score: Optional[float] = None
    injection_score: Optional[float] = None
    embedding: Optional[np.ndarray] = field(default=None, repr=False)

    def as_source(self, ref: int) -> dict:
        return {
            "ref": ref, "document_id": self.document_id, "filename": self.filename, "chunk_index": self.chunk_index,
            "page_number": self.page_number, "section": self.section, "similarity_score": round(float(self.score), 4),
            "text_content": self.text,
        }


@dataclass
class RetrievalStats:
    candidates: int = 0
    after_threshold: int = 0
    embed_ms: float = 0.0
    search_ms: float = 0.0
    rerank_ms: float = 0.0


_pgvector_iterative: Optional[bool] = None


async def _use_hnsw(db: AsyncSession) -> bool:
    """Decide between exact per-tenant search and the HNSW index.

    With a per-user filter, a plain HNSW scan post-filters the index's candidate list and can silently return fewer
    than k rows for a small tenant (measured in PERFORMANCE_REPORT.md on pgvector 0.6). pgvector >= 0.8 fixes this
    with iterative index scans. Default VECTOR_SEARCH=exact gives recall 1.0 on any version and is fast for
    per-user corpus sizes; VECTOR_SEARCH=hnsw is used only when iterative scans are available.
    """
    global _pgvector_iterative
    if settings.VECTOR_SEARCH != "hnsw":
        return False
    if _pgvector_iterative is None:
        ver = (await db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))).scalar() or "0"
        major, minor = (int(x) for x in (ver.split(".") + ["0"])[:2])
        _pgvector_iterative = (major, minor) >= (0, 8)
        if not _pgvector_iterative:
            logger.warning("VECTOR_SEARCH=hnsw needs pgvector >= 0.8 (found %s); using exact per-tenant search.", ver)
    if not _pgvector_iterative:
        return False
    await db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    await db.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
    return True


def _owned_chunks(user_id: int, document_ids: Optional[List[int]]):
    stmt = (
        select(DocumentChunk, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.user_id == user_id, Document.user_id == user_id, Document.status == "indexed")
    )
    if document_ids is not None:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
    return stmt


def _to_result(chunk: DocumentChunk, filename: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id, document_id=chunk.document_id, filename=filename, chunk_index=chunk.chunk_index,
        page_number=chunk.page_number, section=chunk.section, text=chunk.text_content, score=score,
        injection_score=chunk.injection_score,
        embedding=np.asarray(chunk.embedding, dtype=np.float32) if chunk.embedding is not None else None,
    )


def or_tsquery(query: str) -> str:
    """Build an OR tsquery from alphanumeric tokens only, so user input can never break tsquery syntax."""
    tokens = list(dict.fromkeys(t.lower() for t in _TOKEN.findall(query)))[:32]
    return " | ".join(tokens)


class Retriever:
    @classmethod
    async def vector_candidates(cls, db, query_vec, user_id, document_ids, n) -> List[RetrievedChunk]:
        dist = DocumentChunk.embedding.cosine_distance(query_vec)
        # Ordering by `dist + 0` (an expression, not the bare operator) keeps the planner off the HNSW index, so the
        # search is exact over the tenant's rows (found through the user_id index).
        order = dist if await _use_hnsw(db) else dist + 0
        stmt = _owned_chunks(user_id, document_ids).add_columns((1 - dist).label("sim")) \
            .where(DocumentChunk.embedding.isnot(None)).order_by(order).limit(n)
        rows = (await db.execute(stmt)).all()
        out = []
        for chunk, filename, sim in rows:
            r = _to_result(chunk, filename, float(sim))
            r.vector_score = float(sim)
            out.append(r)
        return out

    @classmethod
    async def keyword_candidates(cls, db, query, user_id, document_ids, n) -> List[RetrievedChunk]:
        tsq = or_tsquery(query)
        if not tsq:
            return []
        q = func.to_tsquery("english", tsq)
        # Generated, GIN-indexed column created by database/migrations.py (not mapped on the ORM model).
        tsv_expr = literal_column("document_chunks.tsv")
        rank = func.ts_rank_cd(tsv_expr, q)
        stmt = _owned_chunks(user_id, document_ids).add_columns(rank.label("rank")) \
            .where(tsv_expr.op("@@")(q)).order_by(rank.desc()).limit(n)
        rows = (await db.execute(stmt)).all()
        out = []
        for chunk, filename, rk in rows:
            r = _to_result(chunk, filename, float(rk))
            r.keyword_score = float(rk)
            out.append(r)
        return out

    @staticmethod
    def rrf(lists: List[List[RetrievedChunk]]) -> List[RetrievedChunk]:
        fused: Dict[int, RetrievedChunk] = {}
        scores: Dict[int, float] = {}
        for lst in lists:
            for rank, r in enumerate(lst):
                if r.chunk_id in fused:
                    existing = fused[r.chunk_id]
                    existing.vector_score = existing.vector_score if existing.vector_score is not None else r.vector_score
                    existing.keyword_score = existing.keyword_score if existing.keyword_score is not None else r.keyword_score
                else:
                    fused[r.chunk_id] = r
                scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        ordered = sorted(fused.values(), key=lambda r: scores[r.chunk_id], reverse=True)
        for r in ordered:
            r.score = scores[r.chunk_id]
        return ordered

    @staticmethod
    def mmr(results: List[RetrievedChunk], k: int, lambda_val: float = 0.6) -> List[RetrievedChunk]:
        if len(results) <= 1:
            return results[:k]
        rel = np.array([r.score for r in results], dtype=np.float32)
        rel = (rel - rel.min()) / (rel.max() - rel.min() + 1e-9)
        vecs = [r.embedding for r in results]
        selected = [0]
        while len(selected) < min(k, len(results)):
            best, best_val = -1, -1e9
            for i in range(len(results)):
                if i in selected:
                    continue
                if vecs[i] is None:
                    redundancy = 0.0
                else:
                    redundancy = max(float(np.dot(vecs[i], vecs[j])) for j in selected if vecs[j] is not None) \
                        if any(vecs[j] is not None for j in selected) else 0.0
                val = lambda_val * rel[i] - (1 - lambda_val) * redundancy
                if val > best_val:
                    best, best_val = i, val
            selected.append(best)
        return [results[i] for i in selected]

    @classmethod
    async def search(
        cls,
        db: AsyncSession,
        query: str,
        user_id: int,
        mode: str = "hybrid",
        k: int = 5,
        document_ids: Optional[List[int]] = None,
        apply_threshold: bool = True,
        use_reranker: Optional[bool] = None,
        stats: Optional[RetrievalStats] = None,
    ) -> List[RetrievedChunk]:
        if user_id is None:
            raise ValueError("user_id is required for retrieval (authorisation filter)")
        if document_ids is not None and not document_ids:
            return []
        stats = stats or RetrievalStats()
        use_reranker = settings.RERANKER_ENABLED if use_reranker is None else use_reranker
        mode = (mode or "hybrid").lower()
        n = max(settings.RETRIEVAL_CANDIDATES, k * 3)

        t0 = time.perf_counter()
        qvec = (await embedder.aembed_query(query)).tolist()
        stats.embed_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        vec = await cls.vector_candidates(db, qvec, user_id, document_ids, n)
        if mode == "hybrid":
            kw = await cls.keyword_candidates(db, query, user_id, document_ids, n)
            candidates = cls.rrf([vec, kw])
        else:
            candidates = vec
        stats.search_ms = (time.perf_counter() - t0) * 1000
        stats.candidates = len(candidates)
        if not candidates:
            return []

        if use_reranker:
            t0 = time.perf_counter()
            candidates = candidates[:settings.RERANK_TOP_N]
            passages = [f"{c.section}\n{c.text}" if c.section else c.text for c in candidates]
            scores = await reranker.ascore(query, passages)
            for c, s in zip(candidates, scores):
                c.rerank_score = s
                c.score = s
            candidates.sort(key=lambda c: c.score, reverse=True)
            stats.rerank_ms = (time.perf_counter() - t0) * 1000
            if apply_threshold and candidates:
                floor = max(settings.RERANK_MIN_SCORE, candidates[0].score - settings.RERANK_RELATIVE_MARGIN)
                candidates = [c for c in candidates if c.score >= floor]
        elif apply_threshold:
            candidates = [c for c in candidates if (c.vector_score or 0.0) >= settings.SEMANTIC_MIN_SCORE
                          or (mode == "hybrid" and c.keyword_score)]
        stats.after_threshold = len(candidates)

        if mode == "mmr":
            return cls.mmr(candidates, k)
        return candidates[:k]

    # --- Backwards-compatible wrappers (old call sites/tests) ---
    @classmethod
    async def semantic_search(cls, db, query, k=5, document_ids=None, user_id=None):
        return await cls.search(db, query, user_id=user_id, mode="semantic", k=k, document_ids=document_ids,
                                apply_threshold=False, use_reranker=False)
