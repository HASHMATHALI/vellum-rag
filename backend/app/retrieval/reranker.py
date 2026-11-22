"""Cross-encoder reranker (ms-marco-MiniLM-L-6-v2). Scores are raw logits: > 0 is likely relevant.

Unlike bi-encoder cosine similarity, cross-encoder scores separate relevant from irrelevant passages well enough
to drive the "no relevant context" decision (see RAG_EVALUATION_REPORT.md for the threshold study).
"""
import asyncio
import logging
import threading
from typing import List, Tuple

from starlette.concurrency import run_in_threadpool

from app.config.settings import settings

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str = settings.RERANKER_MODEL):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self._sem = None

    @property
    def model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    import torch
                    from sentence_transformers import CrossEncoder
                    torch.set_num_threads(settings.TORCH_THREADS)
                    logger.info("Loading reranker model %s", self.model_name)
                    self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    def score(self, query: str, passages: List[str]) -> List[float]:
        if not passages:
            return []
        scores = self.model.predict([(query, p) for p in passages], batch_size=16, show_progress_bar=False)
        return [float(s) for s in scores]

    async def ascore(self, query: str, passages: List[str]) -> List[float]:
        # Bound concurrent CPU inference: parallel torch calls on the same cores slow every request down.
        if self._sem is None:
            self._sem = asyncio.Semaphore(settings.MODEL_CONCURRENCY)
        async with self._sem:
            return await run_in_threadpool(self.score, query, passages)


reranker = Reranker()
