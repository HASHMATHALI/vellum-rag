from pydantic import BaseModel, EmailStr, Field, field_validator
from app.auth.jwt import password_problem
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- Auth Schemas ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str = Field(..., min_length=2, description="Name must be at least 2 characters")

    @field_validator("password")
    @classmethod
    def _password_ok(cls, v: str) -> str:
        problem = password_problem(v)
        if problem:
            raise ValueError(problem)
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserInfo(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserInfo

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def _password_ok(cls, v: Optional[str]) -> Optional[str]:
        # previously an empty string was accepted and hashed as the new password
        if v is not None:
            problem = password_problem(v)
            if problem:
                raise ValueError(problem)
        return v

# --- Document Schemas ---
class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    total_chunks: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Chat/Retrieval Schemas ---
class QueryRequest(BaseModel):
    message: str = Field(..., description="The user query text")
    session_id: Optional[str] = Field(None, description="Active session ID or null to start a new chat")
    search_mode: str = Field("semantic", description="Retrieval algorithms: semantic, mmr, or hybrid")
    document_ids: Optional[List[int]] = Field(None, description="Restrict search to specific document IDs")
    k: int = Field(5, ge=1, le=20, description="Top-k chunks to retrieve")

class SourceCitation(BaseModel):
    document_id: int
    filename: str
    chunk_index: int
    page_number: int
    similarity_score: float
    text_content: str

class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    sources: List[SourceCitation]
    created_at: datetime
    # Citation check for assistant messages (see app/retrieval/gloss.py)
    gloss: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Stats / Admin Schemas ---
class SystemStatsResponse(BaseModel):
    total_users: int
    total_documents: int
    storage_used_mb: float
    queries_today: int
    most_asked_questions: List[str]
    api_usage: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    vector_store_size: int
    services: Dict[str, str]
