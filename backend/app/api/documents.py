from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.database.connection import get_db
from app.api.schemas import DocumentResponse
from app.services.document_service import DocumentService
from app.auth.dependencies import get_current_user, get_current_admin
from app.models.user import User

# Empty prefix because these endpoints reside directly on /api/ (e.g. /api/upload, /api/documents)
router = APIRouter(tags=["Documents"])

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Uploads a PDF, DOCX, TXT, or MD file and triggers background RAG indexing."""
    return await DocumentService.upload_document(
        db=db,
        file=file,
        user=current_user,
        background_tasks=background_tasks
    )

@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lists all uploaded documents. Admins see all files; users see only their own."""
    if current_user.role == "admin":
        return await DocumentService.get_all_documents(db)
    return await DocumentService.get_user_documents(db, current_user.id)

@router.delete("/document/{id}", status_code=status.HTTP_200_OK)
async def delete_document(
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a document by ID and removes its vector indexes."""
    await DocumentService.delete_document(db, id, current_user)
    return {"message": "Document deleted and index updated successfully."}

@router.post("/build-index", status_code=status.HTTP_200_OK)
async def rebuild_index(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Admin-only endpoint to rebuild the FAISS vector index from scratch."""
    await DocumentService.rebuild_index(db)
    return {"message": "FAISS vector store successfully rebuilt."}
