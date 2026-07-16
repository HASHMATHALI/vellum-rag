import logging
from typing import List, Dict, Tuple
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from app.embeddings.embedder import embedder
from app.models.document import DocumentChunk

logger = logging.getLogger(__name__)

class Retriever:
    """Advanced Retrieval Engine supporting Semantic Search, MMR, and Hybrid Search using database pgvector."""

    @classmethod
    async def semantic_search(
        cls, 
        db: AsyncSession, 
        query: str, 
        k: int = 5, 
        document_ids: List[int] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """Standard Semantic search using pgvector Cosine Similarity."""
        if document_ids is not None and not document_ids:
            return []
            
        query_vector = embedder.get_embedding(query)
        query_list = query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)

        # 1 - Cosine Distance is Cosine Similarity
        cosine_distance_expr = DocumentChunk.embedding.cosine_distance(query_list)
        stmt = select(DocumentChunk, (1 - cosine_distance_expr).label("similarity"))
        
        if document_ids is not None:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
            
        stmt = stmt.order_by(cosine_distance_expr.asc()).limit(k)
        
        res = await db.execute(stmt)
        raw_results = res.all()
        
        return [(row[0], float(row[1])) for row in raw_results]

    @classmethod
    async def mmr_search(
        cls, 
        db: AsyncSession, 
        query: str, 
        k: int = 5, 
        document_ids: List[int] = None, 
        lambda_val: float = 0.5
    ) -> List[Tuple[DocumentChunk, float]]:
        """Maximal Marginal Relevance search using database pgvector to balance relevance and diversity."""
        if document_ids is not None and not document_ids:
            return []

        query_vector = embedder.get_embedding(query)
        query_list = query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)
        candidate_k = k * 3

        cosine_distance_expr = DocumentChunk.embedding.cosine_distance(query_list)
        stmt = select(DocumentChunk, (1 - cosine_distance_expr).label("similarity"))
        
        if document_ids is not None:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
            
        stmt = stmt.order_by(cosine_distance_expr.asc()).limit(candidate_k)
        
        res = await db.execute(stmt)
        raw_results = res.all()
        
        if not raw_results:
            return []
            
        candidates = []
        candidate_vectors = []
        
        for chunk, score in raw_results:
            if chunk.embedding is not None:
                vec = np.array(chunk.embedding, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                candidates.append((chunk, float(score)))
                candidate_vectors.append(vec)
                
        if not candidates:
            return []
            
        # Select first item (highest semantic similarity)
        selected_indices = [0]
        
        while len(selected_indices) < min(k, len(candidates)):
            best_mmr = -float('inf')
            best_idx = -1
            
            for i in range(len(candidates)):
                if i in selected_indices:
                    continue
                    
                sim_to_query = candidates[i][1]
                
                max_sim_to_selected = -float('inf')
                for sel_idx in selected_indices:
                    sim_to_sel = np.dot(candidate_vectors[i], candidate_vectors[sel_idx])
                    if sim_to_sel > max_sim_to_selected:
                        max_sim_to_selected = sim_to_sel
                        
                mmr_score = lambda_val * sim_to_query - (1 - lambda_val) * max_sim_to_selected
                
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = i
                    
            if best_idx == -1:
                break
            selected_indices.append(best_idx)
            
        return [candidates[idx] for idx in selected_indices]

    @classmethod
    async def hybrid_search(
        cls, 
        db: AsyncSession, 
        query: str, 
        k: int = 5, 
        document_ids: List[int] = None, 
        semantic_weight: float = 0.7
    ) -> List[Tuple[DocumentChunk, float]]:
        """Combines pgvector Semantic Search and database-backed keyword matching."""
        if document_ids is not None and not document_ids:
            return []

        # 1. Semantic Candidates
        semantic_results = await cls.semantic_search(db, query, k=k*2, document_ids=document_ids)
        
        # 2. Keyword Search Candidates using database SQL filtering (ILIKE)
        terms = [t.strip() for t in query.split() if len(t.strip()) > 2]
        keyword_results = []
        if terms:
            conditions = [DocumentChunk.text_content.ilike(f"%{term}%") for term in terms]
            sql_stmt = select(DocumentChunk)
            if document_ids:
                sql_stmt = sql_stmt.where(DocumentChunk.document_id.in_(document_ids))
            
            sql_stmt = sql_stmt.where(or_(*conditions)).limit(k * 2)
            res = await db.execute(sql_stmt)
            keyword_chunks = res.scalars().all()
            
            scored_keyword_chunks = []
            for chunk in keyword_chunks:
                match_count = sum(1 for term in terms if term.lower() in chunk.text_content.lower())
                score = match_count / len(terms)
                scored_keyword_chunks.append((chunk, score))
            
            scored_keyword_chunks.sort(key=lambda x: x[1], reverse=True)
            keyword_results = scored_keyword_chunks

        # 3. Reciprocal Rank Fusion / Weighted Score Combination
        combined_scores: Dict[int, Tuple[DocumentChunk, float]] = {}
        
        sem_max = max([score for _, score in semantic_results]) if semantic_results else 1.0
        sem_min = min([score for _, score in semantic_results]) if semantic_results else 0.0
        sem_range = sem_max - sem_min if sem_max != sem_min else 1.0
        
        for rank, (chunk, score) in enumerate(semantic_results):
            norm_score = (score - sem_min) / sem_range
            combined_scores[chunk.id] = (chunk, norm_score * semantic_weight)
            
        kw_weight = 1.0 - semantic_weight
        kw_max = max([score for _, score in keyword_results]) if keyword_results else 1.0
        kw_min = min([score for _, score in keyword_results]) if keyword_results else 0.0
        kw_range = kw_max - kw_min if kw_max != kw_min else 1.0
        
        for rank, (chunk, score) in enumerate(keyword_results):
            norm_score = (score - kw_min) / kw_range
            added_score = norm_score * kw_weight
            
            if chunk.id in combined_scores:
                current_chunk, current_score = combined_scores[chunk.id]
                combined_scores[chunk.id] = (current_chunk, current_score + added_score)
            else:
                combined_scores[chunk.id] = (chunk, added_score)
                
        sorted_results = list(combined_scores.values())
        sorted_results.sort(key=lambda x: x[1], reverse=True)
        
        return sorted_results[:k]
