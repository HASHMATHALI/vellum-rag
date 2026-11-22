"""The RAG pipeline, shared by the chat API (streaming) and the evaluation suite (non-streaming).

question -> validation -> (reformulation with history) -> embed -> authorised retrieval -> rerank + threshold
-> context build (dedupe, budget, numbered sources) -> grounded generation -> citation validation -> result
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.llm.groq_client import LLMError, LLMUsage, groq_client
from app.models.document import DocumentChunk
from app.observability import tracing
from app.prompts.rag_prompts import CONTEXT_TEMPLATE, NO_ANSWER, SYSTEM_RAG_PROMPT, SYSTEM_REFORMULATE_PROMPT
from app.rag.context import BuiltContext, build_context
from app.rag.guard import prompt_guard_scores
from app.retrieval.retriever import RetrievalStats, RetrievedChunk, Retriever

logger = logging.getLogger(__name__)
MAX_QUESTION_CHARS = 4000

# Questions about the documents as a whole ("what is in my files?", "summarise this document").
_DOCS = r"(?:document|doc|file|pdf|upload|upload(?:ed)?\s+files?|material|text|content)s?"
_OVERVIEW_PATTERNS = [
    re.compile(r"\b(?:summar(?:y|ise|ize|ies)|overview|outline|tl;?dr|gist)\b", re.I),
    re.compile(r"\bwhat\s+(?:kind\s+of\s+|sort\s+of\s+)?(?:information|info|topics?|subjects?|content|data|details)\b.*\b" + _DOCS + r"\b", re.I),
    re.compile(r"\bwhat(?:'s| is| are)\s+(?:in|inside)\s+(?:the|this|these|my)\s+" + _DOCS + r"\b", re.I),
    re.compile(r"\bwhat\s+(?:is|are|'s)\s+(?:the|this|these|my)\s+" + _DOCS + r"\s+about\b", re.I),
    re.compile(r"\b(?:main|key)\s+(?:points|topics|themes|ideas|takeaways)\b", re.I),
    re.compile(r"\bwhat\s+(?:does|do)\s+(?:the|this|these|my)\s+" + _DOCS + r"\s+(?:cover|contain|say|discuss|describe|include)\b", re.I),
]


def is_overview_question(question: str) -> bool:
    q = question.strip()
    return len(q) <= 300 and any(p.search(q) for p in _OVERVIEW_PATTERNS)
_CITATION = re.compile(r"\[(\d{1,3})\]")
_ODD_CITATION = re.compile(r"\[(\d{1,3})[†‡][^\]]*\]")  # e.g. [1†L3-L5]


def normalize_citation_token(tok: str) -> str:
    """Some models emit full-width lenticular brackets (【1】); normalise to [1]."""
    return tok.replace("【", "[").replace("】", "]")


def normalize_citations(answer: str) -> str:
    return _ODD_CITATION.sub(r"[\1]", normalize_citation_token(answer))


@dataclass
class PreparedQuery:
    question: str
    search_query: str
    context: BuiltContext
    messages: List[Dict[str, str]]
    stats: RetrievalStats
    timings: Dict[str, float] = field(default_factory=dict)
    reformulation_usage: Optional[LLMUsage] = None


@dataclass
class RAGResult:
    question: str
    answer: str
    sources: List[dict]
    contexts: List[str]
    search_query: str
    meta: Dict


def validate_question(message: str) -> str:
    q = (message or "").replace("\x00", "").strip()
    if not q:
        raise ValueError("Question must not be empty.")
    if len(q) > MAX_QUESTION_CHARS:
        raise ValueError(f"Question is too long (max {MAX_QUESTION_CHARS} characters).")
    return q


def validate_citations(answer: str, n_sources: int) -> Dict:
    """Remove citations to non-existent sources and report grounding signals."""
    cited = sorted({int(m) for m in _CITATION.findall(answer)})
    invalid = [c for c in cited if c < 1 or c > n_sources]
    refusal = NO_ANSWER.lower()[:40] in answer.lower()
    return {
        "cited_refs": [c for c in cited if c not in invalid],
        "invalid_refs": invalid,
        "is_refusal": refusal,
        "grounding_warning": None if (refusal or (cited and not invalid)) else
        ("invalid_citations" if invalid else "no_citations"),
    }


def strip_invalid_citations(answer: str, invalid: List[int]) -> str:
    for n in invalid:
        answer = answer.replace(f"[{n}]", "")
    return answer


class RAGPipeline:
    def __init__(self, llm=None):
        self.llm = llm or groq_client

    async def reformulate(self, question: str, history: List[Dict[str, str]]) -> (str, Optional[LLMUsage]):
        if not history:
            return question, None
        usage = LLMUsage()
        hist = "\n".join(f"{m['role'].capitalize()}: {m['content'][:800]}" for m in history[-settings.HISTORY_MAX_MESSAGES:])
        with tracing.span("rag.reformulate", "LLM", {"llm.model_name": settings.LLM_UTILITY_MODEL}) as s:
            try:
                q = await self.llm.generate_chat_completion(
                    [{"role": "user", "content": SYSTEM_REFORMULATE_PROMPT.format(chat_history=hist, user_question=question)}],
                    model=settings.LLM_UTILITY_MODEL, max_tokens=200, usage=usage)
            except LLMError:
                return question, None
            q = q.strip().splitlines()[0].strip().strip('"') if q.strip() else ""
            tracing.set_attrs(s, {"llm.token_count.prompt": usage.prompt_tokens,
                                  "llm.token_count.completion": usage.completion_tokens})
            tracing.set_attrs(s, {tracing.INPUT: question, tracing.OUTPUT: q}, content=True)
        return (q if 3 <= len(q) <= 500 else question), usage

    async def _score_injection(self, db: AsyncSession, chunks: List[RetrievedChunk]) -> None:
        if not settings.PROMPT_GUARD_ENABLED:
            return
        todo = [c for c in chunks if c.injection_score is None or c.injection_score < 0.01]
        if not todo:
            return
        scores = await prompt_guard_scores([c.text for c in todo])
        for c, s in zip(todo, scores):
            c.injection_score = max(s, c.injection_score or 0.0)
            await db.execute(update(DocumentChunk).where(DocumentChunk.id == c.chunk_id).values(injection_score=c.injection_score))

    async def prepare(self, db: AsyncSession, user_id: int, question: str, history: List[Dict[str, str]] = None,
                      mode: str = "hybrid", k: int = 5, document_ids: Optional[List[int]] = None) -> PreparedQuery:
        history = history or []
        timings: Dict[str, float] = {}
        t0 = time.perf_counter()
        search_query, r_usage = await self.reformulate(question, history)
        timings["reformulate_ms"] = (time.perf_counter() - t0) * 1000

        stats = RetrievalStats()
        t0 = time.perf_counter()
        with tracing.span("rag.retrieve", "RETRIEVER", {"retrieval.mode": mode, "retrieval.top_k": k}) as s:
            tracing.set_attrs(s, {tracing.INPUT: search_query}, content=True)
            overview = is_overview_question(question)
            if overview:
                # Whole-document questions match no single passage well; give the model a spread of each document.
                chunks = await Retriever.overview(db, user_id, document_ids, max_chunks=max(k, 8), stats=stats)
            else:
                chunks = await Retriever.search(db, search_query, user_id=user_id, mode=mode, k=k,
                                                document_ids=document_ids, stats=stats)
            s.set_attribute("retrieval.overview", overview)
            await self._score_injection(db, chunks)
            s.set_attribute("retrieval.candidates", stats.candidates)
            s.set_attribute("retrieval.after_threshold", stats.after_threshold)
            s.set_attribute("retrieval.embed_ms", round(stats.embed_ms, 2))
            s.set_attribute("retrieval.rerank_ms", round(stats.rerank_ms, 2))
            for i, c in enumerate(chunks):
                p = f"retrieval.documents.{i}.document"
                s.set_attribute(f"{p}.id", f"{c.document_id}:{c.chunk_index}")
                s.set_attribute(f"{p}.score", float(c.score))
                s.set_attribute(f"{p}.metadata", tracing._clean({"filename": c.filename, "page": c.page_number}))
                tracing.set_attrs(s, {f"{p}.content": c.text}, content=True)
        timings["retrieval_ms"] = (time.perf_counter() - t0) * 1000
        timings["overview_mode"] = 1.0 if overview else 0.0
        timings["embed_ms"] = stats.embed_ms
        timings["vector_search_ms"] = stats.search_ms
        timings["rerank_ms"] = stats.rerank_ms

        context = build_context(chunks)
        messages = [{"role": "system", "content": SYSTEM_RAG_PROMPT}]
        for m in history[-settings.HISTORY_MAX_MESSAGES:]:
            messages.append({"role": m["role"], "content": m["content"][:2000]})
        messages.append({"role": "user", "content": CONTEXT_TEMPLATE.format(sources=context.text, question=question)})
        return PreparedQuery(question=question, search_query=search_query, context=context, messages=messages,
                             stats=stats, timings=timings, reformulation_usage=r_usage)

    async def stream(self, prepared: PreparedQuery, meta_out: Dict) -> AsyncGenerator[str, None]:
        """Yields answer tokens and fills `meta_out` (timings, usage, validation) when finished."""
        t_start = time.perf_counter()
        usage = LLMUsage()
        parts: List[str] = []
        if not prepared.context.chunks:
            # Nothing relevant was retrieved: answer deterministically instead of letting the model guess.
            parts.append(NO_ANSWER)
            yield NO_ANSWER
            meta_out.update({"generation_skipped": "no_relevant_context"})
        else:
            with tracing.span("rag.generate", "LLM", {"llm.model_name": settings.LLM_MODEL,
                                                       "llm.invocation_parameters": {"temperature": settings.LLM_TEMPERATURE,
                                                                                     "max_tokens": settings.LLM_MAX_TOKENS}}) as s:
                tracing.set_attrs(s, {"llm.input_messages": prepared.messages}, content=True)
                first = None
                async for tok in self.llm.stream_chat_completion(prepared.messages, usage=usage):
                    tok = normalize_citation_token(tok)
                    if first is None:
                        first = time.perf_counter()
                        meta_out["ttft_ms"] = round((first - t_start) * 1000, 1)
                    parts.append(tok)
                    yield tok
                tracing.set_attrs(s, {"llm.model_name": usage.model, "llm.token_count.prompt": usage.prompt_tokens,
                                      "llm.token_count.completion": usage.completion_tokens,
                                      "llm.token_count.total": usage.total_tokens})
                tracing.set_attrs(s, {tracing.OUTPUT: "".join(parts)}, content=True)
        answer = normalize_citations("".join(parts))
        validation = validate_citations(answer, len(prepared.context.chunks))
        meta_out.update({
            "model": usage.model or None,
            "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
                      "reformulation_tokens": prepared.reformulation_usage.total_tokens if prepared.reformulation_usage else 0},
            "timings_ms": {**{k: round(v, 1) for k, v in prepared.timings.items()},
                           "generation_ms": round((time.perf_counter() - t_start) * 1000, 1)},
            "retrieval": {"candidates": prepared.stats.candidates, "after_threshold": prepared.stats.after_threshold,
                          "context_chunks": len(prepared.context.chunks), "context_tokens": prepared.context.tokens,
                          "dropped_duplicates": prepared.context.dropped_duplicates},
            "validation": validation,
            "search_query": prepared.search_query if prepared.search_query != prepared.question else None,
        })

    async def answer(self, db: AsyncSession, user_id: int, question: str, history: List[Dict[str, str]] = None,
                     mode: str = "hybrid", k: int = 5, document_ids: Optional[List[int]] = None) -> RAGResult:
        question = validate_question(question)
        t0 = time.perf_counter()
        with tracing.span("rag.query", "CHAIN", {"rag.mode": mode, "rag.top_k": k}) as root:
            tracing.set_attrs(root, {tracing.INPUT: question}, content=True)
            prepared = await self.prepare(db, user_id, question, history, mode, k, document_ids)
            meta: Dict = {}
            tokens = [t async for t in self.stream(prepared, meta)]
            answer = normalize_citations("".join(tokens))
            if meta["validation"]["invalid_refs"]:
                answer = strip_invalid_citations(answer, meta["validation"]["invalid_refs"])
            meta["timings_ms"]["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            tracing.set_attrs(root, {tracing.OUTPUT: answer}, content=True)
            root.set_attribute("rag.total_ms", meta["timings_ms"]["total_ms"])
        return RAGResult(question=question, answer=answer, sources=prepared.context.sources,
                         contexts=[c.text for c in prepared.context.chunks], search_query=prepared.search_query, meta=meta)


pipeline = RAGPipeline()
