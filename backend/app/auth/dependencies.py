from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.connection import get_db
from app.auth.jwt import decode_token
from app.models.user import User

# Configure OAuth2PasswordBearer with auto_error=False so missing tokens do not trigger 401s
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Retrieves the logged-in user context.
    If no token is provided, automatically returns the global guest user (role="user").
    If a valid JWT token is provided, decodes the token and returns the corresponding database user.
    """
    if not token:
        # Fall back to guest mode
        email = "guest@vellum.ai"
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if user is None:
            user = User(
                email=email,
                hashed_password="guest_placeholder_password",
                full_name="Guest User",
                role="user",
                is_active=True
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    # A token was provided, validate it
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
        
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
        
    # Query database for user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
        
    return user

async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency to check if user has admin privileges. Re-enables strict access checks."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Insufficient privileges"
        )
    return current_user
