from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.api.schemas import UserRegister, UserLogin, TokenResponse, UserInfo, UserProfileUpdate
from app.services.auth_service import AuthService
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    """Registers a new user in the platform."""
    user = await AuthService.register(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name
    )
    return UserInfo(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role
    )

@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Standard JSON API login endpoint."""
    return await AuthService.login(db=db, email=payload.email, password=payload.password)

@router.post("/token", response_model=TokenResponse, include_in_schema=False)
async def login_oauth_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Fallback OAuth2 form login for Swagger UI compatibility."""
    return await AuthService.login(db=db, email=form_data.username, password=form_data.password)

@router.get("/profile", response_model=UserInfo)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Fetches details of the logged-in user session."""
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role
    )

@router.put("/profile", response_model=UserInfo)
async def update_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Updates user information such as full name or password."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.password is not None:
        from app.auth.jwt import get_password_hash
        current_user.hashed_password = get_password_hash(payload.password)
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role
    )
