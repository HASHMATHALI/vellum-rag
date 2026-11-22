from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Auth ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)
    full_name: str = Field(..., min_length=2, max_length=120)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class MfaLogin(BaseModel):
    mfa_token: str = Field(..., max_length=2048)
    code: str = Field(..., min_length=6, max_length=32)


class UserInfo(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    mfa_enabled: bool = False


class SessionResponse(BaseModel):
    user: UserInfo
    csrf_token: str
    # Also returned for non-browser API clients (Bearer). Browsers should rely on the HttpOnly cookie.
    access_token: Optional[str] = None
    token_type: str = "bearer"


class MfaRequiredResponse(BaseModel):
    mfa_required: Literal[True] = True
    mfa_token: str


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=256)
    new_password: str = Field(..., max_length=256)


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCode(BaseModel):
    code: str = Field(..., min_length=6, max_length=32)


class MfaDisable(BaseModel):
    password: str = Field(..., max_length=256)
    code: str = Field(..., min_length=6, max_length=32)


class AccountDelete(BaseModel):
    password: str = Field(..., max_length=256)


# --- Documents ---
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    total_chunks: int
    error_message: Optional[str] = None
    created_at: datetime


# --- Chat ---
class QueryRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = Field(None, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    search_mode: Literal["semantic", "mmr", "hybrid"] = "hybrid"
    document_ids: Optional[List[int]] = Field(None, max_length=100)
    k: int = Field(5, ge=1, le=10)


class SourceCitation(BaseModel):
    ref: Optional[int] = None
    document_id: int
    filename: str
    chunk_index: int
    page_number: int
    section: Optional[str] = None
    similarity_score: float
    text_content: str
    cited: Optional[bool] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    session_id: str
    role: str
    content: str
    sources: List[SourceCitation]
    created_at: datetime
    # Citation check for assistant messages (see app/retrieval/gloss.py)
    gloss: Optional[Dict[str, Any]] = None


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime


# --- Admin ---
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
