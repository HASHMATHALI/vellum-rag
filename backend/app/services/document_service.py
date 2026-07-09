import os
import shutil
import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import UploadFile, HTTPException, status
from app.config.settings import settings
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.ingestion.parser import FileParser
from app.ingestion.chunker import TextChunker
from app.embeddings.embedder import embedder
from app.vectorstore.faiss_store import vector_store

logger = logging.getLogger(__name__)

class DocumentService:
    """Service to manage file upload, parsing, embedding generation, indexing, and deletions."""

    @staticmethod
    async def get_user_documents(db: AsyncSession, user_id: int) -> List[Document]:
        """Fetch all documents belonging to a user."""
        result = await db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_all_documents(db: AsyncSession) -> List[Document]:
        """Fetch all documents in the system (for Admin)."""
        result = await db.execute(select(Document).order_by(Document.created_at.desc()))
        return list(result.scalars().all())

    @classmethod
    async def upload_document(
        cls, 
        db: AsyncSession, 
        file: UploadFile, 
        user: User, 
        background_tasks
    ) -> Document:
        """Saves file to disk, logs DB entry and schedules async parsing and indexing."""
        # Check file extension
        ext = os.path.splitext(file.filename)[1].lower().strip(".")
        if ext not in ["pdf", "docx", "txt", "md"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format: .{ext}"
            )
            
        # Ensure upload folder exists
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        # Save file to disk
        filepath = os.path.join(settings.UPLOAD_DIR, f"{user.id}_{int(os.urandom(4).hex(), 16)}_{file.filename}")
        try:
            with open(filepath, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except Exception as e:
            logger.error(f"Failed to write file to disk ({e})")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not save file to disk."
            )
            
        file_size = os.path.getsize(filepath)
        
        # Log to Database
        db_doc = Document(
            filename=file.filename,
            filepath=filepath,
            file_type=ext,
            file_size=file_size,
            user_id=user.id,
            status="processing"
        )
        db.add(db_doc)
        await db.commit()
        await db.refresh(db_doc)
        
        # Run indexing in the background
        background_tasks.add_task(cls._process_and_index_document, db_doc.id)
        
        return db_doc

    @classmethod
    async def _process_and_index_document(cls, document_id: int):
        """Background worker to extract text, chunk, embed, and load into FAISS."""
        # Since this runs as background task in thread pool, create a separate DB session
        from app.database.connection import async_session
        
        async with async_session() as db:
            try:
                # Fetch document
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalars().first()
                if not doc:
                    logger.error(f"Background Process: Document {document_id} not found.")
                    return
                
                # 1. Parse File
                parsed_pages = FileParser.parse(doc.filepath, doc.file_type)
                if not parsed_pages:
                    raise ValueError("No text could be extracted from this document.")
                
                # 2. Chunk text
                chunker = TextChunker()
                chunks = chunker.chunk_document(parsed_pages)
                if not chunks:
                    raise ValueError("No chunks generated from the document text.")
                
                # 3. Save chunks to DB first to acquire primary key IDs
                db_chunks = []
                for ch in chunks:
                    db_chunk = DocumentChunk(
                        document_id=doc.id,
                        chunk_index=ch["chunk_index"],
                        text_content=ch["text_content"],
                        page_number=ch["page_number"]
                    )
                    db.add(db_chunk)
                await db.flush() # Flush to populate db_chunk.id without committing transaction yet
                
                # 4. Generate Embeddings and Add to FAISS using chunk.id
                texts = [ch.text_content for ch in db_chunks]
                embeddings = embedder.get_embeddings(texts)
                chunk_ids = [ch.id for ch in db_chunks]
                
                # Save into FAISS
                vector_store.add_vectors(embeddings, chunk_ids)
                
                # Update Document status
                doc.status = "indexed"
                doc.total_chunks = len(db_chunks)
                db.add(doc)
                await db.commit()
                logger.info(f"Background Process: Successfully indexed document {doc.filename} (ID: {doc.id})")
                
            except Exception as e:
                logger.error(f"Background Process failed for Document {document_id}: {e}", exc_info=True)
                # Mark document as failed
                try:
                    result = await db.execute(select(Document).where(Document.id == document_id))
                    doc = result.scalars().first()
                    if doc:
                        doc.status = "failed"
                        db.add(doc)
                        await db.commit()
                except Exception as rollback_err:
                    logger.error(f"Failed to update document status to FAILED: {rollback_err}")

    @staticmethod
    async def delete_document(db: AsyncSession, document_id: int, user: User) -> bool:
        """Removes a document from Postgres and deletes its vectors from FAISS."""
        # Fetch document
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalars().first()
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
            
        # Permission check
        if user.role != "admin" and doc.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this document."
            )
            
        # Get all chunk IDs
        chunks_res = await db.execute(
            select(DocumentChunk.id).where(DocumentChunk.document_id == doc.id)
        )
        chunk_ids = list(chunks_res.scalars().all())
        
        # 1. Delete from FAISS
        if chunk_ids:
            try:
                vector_store.delete_vectors(chunk_ids)
            except Exception as e:
                logger.error(f"Failed to remove vectors for document {document_id}: {e}")
                
        # 2. Delete physical file
        if os.path.exists(doc.filepath):
            try:
                os.remove(doc.filepath)
            except Exception as e:
                logger.error(f"Failed to delete document file {doc.filepath}: {e}")
                
        # 3. Delete from DB (chunks cascade delete automatically)
        await db.delete(doc)
        await db.commit()
        return True

    @classmethod
    async def rebuild_index(cls, db: AsyncSession) -> bool:
        """Admin function to erase FAISS and index all existing chunks from the database."""
        # Fetch all successful chunks in database
        result = await db.execute(
            select(DocumentChunk)
            .join(Document)
            .where(Document.status == "indexed")
        )
        chunks = result.scalars().all()
        
        # Clear current FAISS index
        vector_store.clear()
        
        if not chunks:
            return True
            
        # Process in batches to avoid RAM overflow
        batch_size = 256
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text_content for c in batch]
            ids = [c.id for c in batch]
            
            embeddings = embedder.get_embeddings(texts)
            vector_store.add_vectors(embeddings, ids)
            
        vector_store.save_index()
        return True
