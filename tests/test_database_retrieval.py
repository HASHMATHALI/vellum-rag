import sys
import os
import pytest
import numpy as np
from sqlalchemy.future import select

# Ensure app modules are importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database.connection import async_session
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.models.document import Document, DocumentChunk
from app.retrieval.retriever import Retriever

@pytest.mark.asyncio
async def test_database_and_vector_retrieval():
    async with async_session() as db:
        # 1. Create a dummy user first to satisfy foreign key constraints
        user = User(
            email="test_integration@example.com",
            hashed_password="hashed_password_placeholder",
            full_name="Integration Test User",
            role="user"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # 2. Create a dummy document linked to this user
        doc = Document(
            filename="integration_test.txt",
            filepath="/tmp/integration_test.txt",
            file_type="txt",
            file_size=100,
            user_id=user.id,
            status="indexed"
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        
        # 3. Add two chunks with specific text and embeddings
        # We use a 384-dimensional vector (all miniLM size)
        emb1 = np.zeros(384, dtype=np.float32)
        emb1[0] = 1.0  # Vector pointing along axis 0
        
        emb2 = np.zeros(384, dtype=np.float32)
        emb2[1] = 1.0  # Vector pointing along axis 1
        
        chunk1 = DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            text_content="This is the target chunk talking about rockets.",
            page_number=1,
            embedding=emb1.tolist()
        )
        chunk2 = DocumentChunk(
            document_id=doc.id,
            chunk_index=1,
            text_content="This is a second chunk discussing history.",
            page_number=1,
            embedding=emb2.tolist()
        )
        db.add(chunk1)
        db.add(chunk2)
        await db.commit()
        
        try:
            # 4. Direct pgvector SQL selection using cosine similarity
            # We select chunks ordering by cosine distance to query_vector
            query_vector = np.zeros(384, dtype=np.float32)
            query_vector[0] = 0.9  # Query closest to chunk1 (cosine similarity ~ 1.0)
            
            result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc.id)
                .order_by(DocumentChunk.embedding.cosine_distance(query_vector.tolist()))
                .limit(1)
            )
            closest_chunk = result.scalars().first()
            
            assert closest_chunk is not None
            assert closest_chunk.text_content == "This is the target chunk talking about rockets."
            
            # 5. Clean up by deleting the user
            # Check cascade delete on the document & chunks works
            await db.delete(user)
            await db.commit()
            
            # Check chunks are gone
            check_result = await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            remaining_chunks = check_result.scalars().all()
            assert len(remaining_chunks) == 0
            
            # Check document is gone
            check_doc_result = await db.execute(
                select(Document).where(Document.id == doc.id)
            )
            remaining_docs = check_doc_result.scalars().all()
            assert len(remaining_docs) == 0
            
        except Exception as e:
            # Clean up user and document if test fails
            await db.delete(user)
            await db.commit()
            raise e
