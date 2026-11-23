import hashlib
import logging
from typing import List

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.database.connection import system_session
from app.embeddings.embedder import embedder
from app.ingestion import storage
from app.ingestion.chunker import TextChunker
from app.ingestion.parser import ParseError, parse
from app.ingestion.validation import read_upload_limited, sanitize_filename, validate_upload
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.observability import tracing
from app.rag.guard import heuristic_score

logger = logging.getLogger(__name__)


class DocumentService:
    @staticmethod
    async def get_user_documents(db: AsyncSession, user_id: int) -> List[Document]:
        res = await db.execute(select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def get_all_documents(db: AsyncSession) -> List[Document]:
        res = await db.execute(select(Document).order_by(Document.created_at.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def get_owned(db: AsyncSession, document_id: int, user: User, allow_admin: bool = False) -> Document:
        doc = await db.get(Document, document_id)
        # 404 (not 403) for other users' documents, so IDs cannot be probed.
        if doc is None or (doc.user_id != user.id and not (allow_admin and user.role == "admin")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
        return doc

    @classmethod
    async def upload_document(cls, db: AsyncSession, file: UploadFile, user: User, background_tasks) -> Document:
        display_name = sanitize_filename(file.filename or "")
        data = await read_upload_limited(file)
        ext = validate_upload(display_name, file.content_type, data)
        digest = hashlib.sha256(data).hexdigest()

        if user.role == "guest":
            count = (await db.execute(select(func.count(Document.id)).where(Document.user_id == user.id))).scalar() or 0
            if count >= settings.GUEST_MAX_DOCUMENTS:
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    f"Guest accounts can upload up to {settings.GUEST_MAX_DOCUMENTS} documents. Sign up for more.")
        dup = (await db.execute(select(Document).where(Document.user_id == user.id, Document.content_hash == digest))).scalars().first()
        if dup:
            raise HTTPException(status.HTTP_409_CONFLICT, f"This file was already uploaded as '{dup.filename}'.")

        try:
            ref = await run_in_threadpool(storage.save, user.id, data, ext, file.content_type or "application/octet-stream")
        except storage.StorageError:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not store the file. Please try again.")

        doc = Document(filename=display_name, filepath=ref, file_type=ext, file_size=len(data), content_hash=digest,
                       user_id=user.id, status="processing")
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        if settings.INLINE_INDEXING:
            await cls.process_and_index_document(doc.id)
            await db.refresh(doc)
        else:
            background_tasks.add_task(cls.process_and_index_document, doc.id)
        return doc

    @staticmethod
    def _extract_and_chunk(data: bytes, file_type: str) -> List[dict]:
        blocks = parse(data, file_type)
        chunks = TextChunker().chunk_document(blocks)
        if not chunks:
            raise ParseError("No text chunks could be produced from this document.")
        return chunks

    @classmethod
    async def index_bytes(cls, db: AsyncSession, doc: Document, data: bytes) -> int:
        """Parse, chunk, embed and store chunks for `doc` (replacing any existing chunks). Used by upload and rebuild."""
        with tracing.span("ingest.document", "CHAIN", {"document.id": doc.id, "document.type": doc.file_type,
                                                        "document.bytes": len(data)}) as s:
            chunks = await run_in_threadpool(cls._extract_and_chunk, data, doc.file_type)
            texts = [f"{c['section']}\n{c['text_content']}" if c.get("section") else c["text_content"] for c in chunks]
            with tracing.span("ingest.embed", "EMBEDDING", {"embedding.model_name": settings.EMBEDDING_MODEL,
                                                             "embedding.count": len(texts)}):
                embeddings = await embedder.aembed_documents(texts)
            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
            for c, emb in zip(chunks, embeddings):
                db.add(DocumentChunk(document_id=doc.id, user_id=doc.user_id, chunk_index=c["chunk_index"],
                                     text_content=c["text_content"], page_number=c["page_number"],
                                     section=c.get("section"), injection_score=heuristic_score(c["text_content"]),
                                     embedding=emb.tolist()))
            doc.status = "indexed"
            doc.total_chunks = len(chunks)
            doc.error_message = None
            await db.commit()
            s.set_attribute("document.chunks", len(chunks))
            return len(chunks)

    @classmethod
    async def process_and_index_document(cls, document_id: int) -> None:
        async with system_session() as db:
            doc = await db.get(Document, document_id)
            if doc is None:
                return
            try:
                data = await run_in_threadpool(storage.load, doc.filepath)
                n = await cls.index_bytes(db, doc, data)
                logger.info("Indexed document id=%s (%d chunks)", doc.id, n)
            except Exception as e:
                await db.rollback()
                doc = await db.get(Document, document_id)
                if doc is None:
                    return
                doc.status = "failed"
                doc.total_chunks = 0
                doc.error_message = str(e)[:500] if isinstance(e, (ParseError, storage.StorageError)) else \
                    "Indexing failed due to an internal error."
                await db.commit()
                logger.error("Indexing failed for document id=%s: %s", document_id, type(e).__name__,
                             exc_info=not isinstance(e, ParseError))

    @staticmethod
    async def delete_document(db: AsyncSession, document_id: int, user: User) -> None:
        doc = await DocumentService.get_owned(db, document_id, user, allow_admin=True)
        ref = doc.filepath
        await db.delete(doc)  # chunks + embeddings cascade (ON DELETE CASCADE)
        await db.commit()
        await run_in_threadpool(storage.delete, ref)

    @classmethod
    async def reindex(cls, db: AsyncSession, doc: Document) -> None:
        data = await run_in_threadpool(storage.load, doc.filepath)
        await cls.index_bytes(db, doc, data)

    @classmethod
    async def rebuild_index(cls) -> dict:
        ok, failed = 0, 0
        async with system_session() as db:
            docs = (await db.execute(select(Document).where(Document.status.in_(["indexed", "failed"])))).scalars().all()
            for doc in docs:
                try:
                    await cls.reindex(db, doc)
                    ok += 1
                except Exception as e:
                    await db.rollback()
                    failed += 1
                    logger.error("Rebuild failed for document id=%s: %s", doc.id, type(e).__name__)
        return {"reindexed": ok, "failed": failed}
