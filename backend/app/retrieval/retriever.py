import logging
from typing import List, Dict, Tuple
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.embeddings.embedder import embedder
from app.vectorstore.faiss_store import vector_store
from app.models.document import DocumentChunk

logger = logging.getLogger(__name__)

class Retriever:
    """Advanced Retrieval Engine supporting Semantic Search, MMR, and Hybrid Search."""

    @staticmethod
    async def get_chunks_by_ids(db: AsyncSession, chunk_ids: List[int]) -> Dict[int, DocumentChunk]:
        """Fetch DocumentChunk models from DB for a list of primary key IDs."""
        if not chunk_ids:
            return {}
        result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.id.in_(chunk_ids))
        )
        chunks = result.scalars().all()
        return {chunk.id: chunk for chunk in chunks}

    @classmethod
    async def semantic_search(
        cls, 
        db: AsyncSession, 
        query: str, 
        k: int = 5, 
        document_ids: List[int] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """Standard Semantic search using FAISS Cosine Similarity (IP)."""
        query_vector = embedder.get_embedding(query)
        # Search a wider pool if filtering is applied, to account for filtered-out results
        search_k = k * 3 if document_ids else k
        
        raw_results = vector_store.search(query_vector, search_k)
        if not raw_results:
            return []
            
        chunk_ids = [idx for idx, _ in raw_results]
        db_chunks = await cls.get_chunks_by_ids(db, chunk_ids)
        
        final_results = []
        for chunk_id, score in raw_results:
            chunk = db_chunks.get(chunk_id)
            if chunk:
                # If document filter list is provided, verify match
                if document_ids is not None and chunk.document_id not in document_ids:
                    continue
                final_results.append((chunk, score))
                if len(final_results) == k:
                    break
                    
        return final_results

    @classmethod
    async def mmr_search(
        cls, 
        db: AsyncSession, 
        query: str, 
        k: int = 5, 
        document_ids: List[int] = None, 
        lambda_val: float = 0.5
    ) -> List[Tuple[DocumentChunk, float]]:
        """Maximal Marginal Relevance search to balance relevance and chunk diversity."""
        query_vector = embedder.get_embedding(query)
        # Fetch candidate pool (e.g., 3 * k candidates)
        candidate_k = k * 3
        raw_results = vector_store.search(query_vector, candidate_k)
        
        if not raw_results:
            return []
            
        chunk_ids = [idx for idx, _ in raw_results]
        db_chunks = await cls.get_chunks_by_ids(db, chunk_ids)
        
        # Filter candidates by allowed document IDs and structure them
        candidates = []
        candidate_vectors = []
        
        # Normalize query vector for cosine calculations
        q_vec = query_vector / np.linalg.norm(query_vector)
        
        for chunk_id, score in raw_results:
            chunk = db_chunks.get(chunk_id)
            if chunk:
                if document_ids is not None and chunk.document_id not in document_ids:
                    continue
                
                # Reconstruct vector from FAISS or re-embed if reconstruction fails
                try:
                    # IndexIDMap -> IndexFlatIP. Reconstruct is supported
                    vec = vector_store.index.reconstruct(chunk_id)
                except Exception:
                    # Fallback to generating embedding if reconstruction fails
                    vec = embedder.get_embedding(chunk.text_content)
                
                vec = vec / np.linalg.norm(vec)
                candidates.append((chunk, score))
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
                    
                # Calculate similarity to query (pre-calculated score)
                sim_to_query = candidates[i][1]
                
                # Calculate max similarity to already selected candidates
                max_sim_to_selected = -float('inf')
                for sel_idx in selected_indices:
                    sim_to_sel = np.dot(candidate_vectors[i], candidate_vectors[sel_idx])
                    if sim_to_sel > max_sim_to_selected:
                        max_sim_to_selected = sim_to_sel
                        
                # MMR formula
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
        """Combines FAISS Semantic Search and SQL text-based keyword matching."""
        # 1. Semantic Candidates
        semantic_results = await cls.semantic_search(db, query, k=k*2, document_ids=document_ids)
        
        # 2. Keyword Search Candidates
        # Split terms to search database chunks using SQL ILIKE
        terms = [t.strip() for t in query.split() if len(t.strip()) > 2]
        keyword_results = []
        if terms:
            # Build dynamic search queries for document chunks
            # In production, we'd use pg_trgm or PostgreSQL Full-Text Search.
            # Here we use an async query for matching terms.
            sql_stmt = select(DocumentChunk)
            if document_ids:
                sql_stmt = sql_stmt.where(DocumentChunk.document_id.in_(document_ids))
            
            # Simple keyword matching across document content
            # We can find matches that contain at least one term
            # and count matches for scoring
            res = await db.execute(sql_stmt)
            all_chunks = res.scalars().all()
            
            scored_keyword_chunks = []
            for chunk in all_chunks:
                match_count = sum(1 for term in terms if term.lower() in chunk.text_content.lower())
                if match_count > 0:
                    # Simple keyword matching score normalized by terms count
                    score = match_count / len(terms)
                    scored_keyword_chunks.append((chunk, score))
            
            # Sort by keyword score descending
            scored_keyword_chunks.sort(key=lambda x: x[1], reverse=True)
            keyword_results = scored_keyword_chunks[:k*2]

        # 3. Reciprocal Rank Fusion / Weighted Score Combination
        # Create a dict of chunk_id -> (chunk_model, combined_score)
        combined_scores: Dict[int, Tuple[DocumentChunk, float]] = {}
        
        # Normalize semantic scores to range [0, 1] if not already
        sem_max = max([score for _, score in semantic_results]) if semantic_results else 1.0
        sem_min = min([score for _, score in semantic_results]) if semantic_results else 0.0
        sem_range = sem_max - sem_min if sem_max != sem_min else 1.0
        
        for rank, (chunk, score) in enumerate(semantic_results):
            norm_score = (score - sem_min) / sem_range
            combined_scores[chunk.id] = (chunk, norm_score * semantic_weight)
            
        # Add keyword scores
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
                
        # Sort and return top k
        sorted_results = list(combined_scores.values())
        sorted_results.sort(key=lambda x: x[1], reverse=True)
        
        return sorted_results[:k]
