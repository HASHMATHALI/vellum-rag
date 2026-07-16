import os
import logging
from typing import List
from urllib.parse import unquote
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import UploadFile, HTTPException, status
from app.config.settings import settings
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.ingestion.parser import FileParser
from app.ingestion.chunker import TextChunker
from app.embeddings.embedder import embedder
from supabase import create_client

logger = logging.getLogger(__name__)

def get_supabase_client():
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        try:
            return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
    return None

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
        """Saves file to Supabase Storage (or disk locally), logs DB entry and schedules RAG indexing."""
        # Check file extension
        ext = os.path.splitext(file.filename)[1].lower().strip(".")
        if ext not in ["pdf", "docx", "txt", "md"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format: .{ext}"
            )
            
        file_size = 0
        filepath = ""
        supabase_client = get_supabase_client()
        
        if supabase_client:
            # Upload directly to Supabase Storage
            filename_clean = f"{user.id}_{int(os.urandom(4).hex(), 16)}_{file.filename}"
            supabase_path = f"{user.id}/{filename_clean}"
            try:
                file_content = await file.read()
                file_size = len(file_content)
                
                # Upload to Supabase Bucket
                supabase_client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                    path=supabase_path,
                    file=file_content,
                    file_options={"content-type": file.content_type or "application/octet-stream"}
                )
                
                # Get the Public URL of the uploaded asset
                filepath = supabase_client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(supabase_path)
            except Exception as e:
                logger.error(f"Failed to upload file to Supabase Storage: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Could not upload file to cloud storage: {e}"
                )
        else:
            # Fall back to local file storage
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            filepath = os.path.join(settings.UPLOAD_DIR, f"{user.id}_{int(os.urandom(4).hex(), 16)}_{file.filename}")
            try:
                await file.seek(0)
                file_content = await file.read()
                file_size = len(file_content)
                with open(filepath, "wb") as f:
                    f.write(file_content)
            except Exception as e:
                logger.error(f"Failed to write file to local disk: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not save file to local disk."
                )
            
        # Log metadata to PostgreSQL
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
        """Background worker to extract text, chunk, embed, and load into pgvector."""
        from app.database.connection import async_session
        
        async with async_session() as db:
            try:
                # Fetch document
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalars().first()
                if not doc:
                    logger.error(f"Background Process: Document {document_id} not found.")
                    return
                
                # 1. Parse File (remotely from Supabase URL or locally from filepath)
                parsed_pages = FileParser.parse(doc.filepath, doc.file_type)
                if not parsed_pages:
                    raise ValueError("No text could be extracted from this document.")
                
                # 2. Chunk text
                chunker = TextChunker()
                chunks = chunker.chunk_document(parsed_pages)
                if not chunks:
                    raise ValueError("No chunks generated from the document text.")
                
                # 3. Save chunks to DB
                db_chunks = []
                for ch in chunks:
                    db_chunk = DocumentChunk(
                        document_id=doc.id,
                        chunk_index=ch["chunk_index"],
                        text_content=ch["text_content"],
                        page_number=ch["page_number"]
                    )
                    db.add(db_chunk)
                    db_chunks.append(db_chunk)
                await db.flush()
                
                # 4. Generate Embeddings and Save Directly to Database Chunks
                texts = [ch.text_content for ch in db_chunks]
                embeddings = embedder.get_embeddings(texts)
                
                for ch, emb in zip(db_chunks, embeddings):
                    emb_list = emb.tolist() if hasattr(emb, "tolist") else list(emb)
                    ch.embedding = emb_list
                    db.add(ch)
                
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
                        doc.total_chunks = 0
                        db.add(doc)
                        await db.commit()
                except Exception as rollback_err:
                    logger.error(f"Failed to update document status to FAILED: {rollback_err}")

    @staticmethod
    async def delete_document(db: AsyncSession, document_id: int, user: User) -> bool:
        """Removes a document from Postgres and deletes its file from storage bucket."""
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
            
        # 1. Delete file from Storage (Supabase or Local)
        if doc.filepath.startswith("http://") or doc.filepath.startswith("https://"):
            supabase_client = get_supabase_client()
            if supabase_client:
                try:
                    bucket_name = settings.SUPABASE_STORAGE_BUCKET
                    part_to_find = f"/public/{bucket_name}/"
                    if part_to_find in doc.filepath:
                        storage_path = doc.filepath.split(part_to_find)[1]
                        storage_path = unquote(storage_path)
                        supabase_client.storage.from_(bucket_name).remove([storage_path])
                        logger.info(f"Deleted remote file {storage_path} from Supabase Storage.")
                except Exception as e:
                    logger.error(f"Failed to delete file from Supabase Storage: {e}")
        else:
            if os.path.exists(doc.filepath):
                try:
                    os.remove(doc.filepath)
                except Exception as e:
                    logger.error(f"Failed to delete local document file {doc.filepath}: {e}")
                
        # 2. Delete from DB (chunks and vector embeddings cascade delete automatically)
        await db.delete(doc)
        await db.commit()
        return True

    @classmethod
    async def rebuild_index(cls, db: AsyncSession) -> bool:
        """Admin function to fully re-parse, re-chunk, and re-embed all documents in PostgreSQL from scratch."""
        result = await db.execute(
            select(Document)
            .where(Document.status == "indexed")
        )
        documents = result.scalars().all()
        
        if not documents:
            return True
            
        from sqlalchemy import delete
        
        for doc in documents:
            try:
                # 1. Delete existing chunks for this document
                await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
                
                # 2. Re-parse File
                parsed_pages = FileParser.parse(doc.filepath, doc.file_type)
                if not parsed_pages:
                    logger.error(f"Rebuild Index: No text extracted from {doc.filename}")
                    continue
                    
                # 3. Re-chunk text
                chunker = TextChunker()
                chunks = chunker.chunk_document(parsed_pages)
                if not chunks:
                    logger.error(f"Rebuild Index: No chunks generated from {doc.filename}")
                    continue
                    
                # 4. Save and embed new chunks
                db_chunks = []
                for ch in chunks:
                    db_chunk = DocumentChunk(
                        document_id=doc.id,
                        chunk_index=ch["chunk_index"],
                        text_content=ch["text_content"],
                        page_number=ch["page_number"]
                    )
                    db.add(db_chunk)
                    db_chunks.append(db_chunk)
                await db.flush()
                
                # Generate embeddings
                texts = [ch.text_content for ch in db_chunks]
                embeddings = embedder.get_embeddings(texts)
                
                for ch, emb in zip(db_chunks, embeddings):
                    emb_list = emb.tolist() if hasattr(emb, "tolist") else list(emb)
                    ch.embedding = emb_list
                    db.add(ch)
                
                # Update total chunks count
                doc.total_chunks = len(db_chunks)
                db.add(doc)
                await db.commit()
                logger.info(f"Rebuild Index: Successfully re-chunked and re-indexed {doc.filename} (Chunks: {len(db_chunks)})")
                
            except Exception as e:
                logger.error(f"Rebuild Index: Failed to re-index {doc.filename}: {e}", exc_info=True)
                
        return True
