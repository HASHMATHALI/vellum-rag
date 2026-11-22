from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DocumentResponse
from app.auth.dependencies import get_current_admin, get_current_user
from app.database.connection import get_db
from app.middleware.rate_limiter import rate_limit_user
from app.models.user import User
from app.services.document_service import DocumentService

router = APIRouter(tags=["Documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit_user("upload", 30, 3600))])
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                      current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Uploads a PDF, DOCX, TXT, MD or CSV file and schedules background indexing."""
    return await DocumentService.upload_document(db, file, current_user, background_tasks)


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Lists the caller's documents. Admins see all documents (metadata only)."""
    if current_user.role == "admin":
        return await DocumentService.get_all_documents(db)
    return await DocumentService.get_user_documents(db, current_user.id)


@router.get("/document/{id}", response_model=DocumentResponse)
async def get_document(id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await DocumentService.get_owned(db, id, current_user, allow_admin=True)


@router.delete("/document/{id}", status_code=status.HTTP_200_OK)
async def delete_document(id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Deletes a document, its stored file, chunks and embeddings."""
    await DocumentService.delete_document(db, id, current_user)
    return {"message": "Document deleted and index updated successfully."}


@router.post("/build-index", status_code=status.HTTP_200_OK,
             dependencies=[Depends(rate_limit_user("rebuild", 2, 3600))])
async def rebuild_index(current_user: User = Depends(get_current_admin)):
    """Admin-only: re-parse, re-chunk and re-embed all documents (e.g. after changing chunking or the model)."""
    result = await DocumentService.rebuild_index()
    return {"message": "Vector store rebuilt.", **result}
