from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (AccountDelete, MfaCode, MfaDisable, MfaLogin, MfaRequiredResponse, MfaSetupResponse,
                             PasswordChange, SessionResponse, UserInfo, UserLogin, UserProfileUpdate, UserRegister)
from app.auth import mfa
from app.auth.dependencies import (ACCESS_COOKIE, REFRESH_COOKIE, get_current_user, get_registered_user)
from app.auth.jwt import create_mfa_token, csrf_token_for, decode_token, get_password_hash, verify_password
from app.config.settings import settings
from app.database.connection import get_db
from app.ingestion import storage
from app.middleware.rate_limiter import rate_limit_ip, rate_limit_key, rate_limit_user
from app.models.document import Document
from app.models.user import User
from app.services.auth_service import AuthService, validate_password_strength

router = APIRouter(prefix="/auth", tags=["Authentication"])


def user_info(u: User) -> UserInfo:
    return UserInfo(id=u.id, email=u.email if u.role != "guest" else "guest", full_name=u.full_name, role=u.role,
                    mfa_enabled=bool(u.mfa_enabled))


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    common = dict(httponly=True, secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE,
                  domain=settings.COOKIE_DOMAIN or None)
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/api", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                        path="/api/auth", **common)


def _clear_auth_cookies(response: Response) -> None:
    for name, path in ((ACCESS_COOKIE, "/api"), (REFRESH_COOKIE, "/api/auth")):
        response.delete_cookie(name, path=path, domain=settings.COOKIE_DOMAIN or None,
                               secure=settings.COOKIE_SECURE, httponly=True, samesite=settings.COOKIE_SAMESITE)


async def _start_session(db: AsyncSession, user: User, request: Request, response: Response) -> SessionResponse:
    access, refresh, s = await AuthService.create_session(db, user, request.headers.get("user-agent", ""))
    _set_auth_cookies(response, access, refresh)
    return SessionResponse(user=user_info(user), csrf_token=csrf_token_for(s.id), access_token=access)


@router.post("/register", response_model=UserInfo, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit_ip("register", 5, 3600))])
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    user = await AuthService.register(db, payload.email, payload.password, payload.full_name)
    return user_info(user)


@router.post("/login", response_model=Union[SessionResponse, MfaRequiredResponse],
             dependencies=[Depends(rate_limit_ip("login", 10, 60))])
async def login(payload: UserLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Per-account limit as well, to slow distributed brute force against one e-mail.
    await rate_limit_key(f"login:acct:{payload.email.lower()}", 10, 900)
    user = await AuthService.authenticate(db, payload.email, payload.password)
    if user.mfa_enabled:
        await db.commit()
        return MfaRequiredResponse(mfa_token=create_mfa_token(user.id))
    return await _start_session(db, user, request, response)


@router.post("/login/mfa", response_model=SessionResponse, dependencies=[Depends(rate_limit_ip("mfa", 10, 300))])
async def login_mfa(payload: MfaLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    claims = decode_token(payload.mfa_token, "mfa")
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA session expired. Sign in again.")
    await rate_limit_key(f"mfa:user:{claims['sub']}", 5, 300)
    user = await db.get(User, int(claims["sub"]))
    if user is None or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA session expired. Sign in again.")
    if not await AuthService.verify_second_factor(db, user, payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication code.")
    return await _start_session(db, user, request, response)


@router.post("/guest", response_model=SessionResponse, dependencies=[Depends(rate_limit_ip("guest", 10, 3600))])
async def guest(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Creates an isolated, short-lived anonymous account (data purged after GUEST_TTL_HOURS)."""
    user = await AuthService.create_guest(db)
    return await _start_session(db, user, request, response)


@router.post("/refresh", response_model=SessionResponse, dependencies=[Depends(rate_limit_ip("refresh", 30, 60))])
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user, access, new_refresh, s = await AuthService.rotate_refresh(db, token)
    _set_auth_cookies(response, access, new_refresh)
    return SessionResponse(user=user_info(user), csrf_token=csrf_token_for(s.id), access_token=access)


@router.get("/session", response_model=SessionResponse)
async def session_info(request: Request, current_user: User = Depends(get_current_user)):
    return SessionResponse(user=user_info(current_user), csrf_token=csrf_token_for(request.state.session_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, current_user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    await AuthService.revoke_session(db, request.state.session_id)
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/profile", response_model=UserInfo)
async def get_profile(current_user: User = Depends(get_current_user)):
    return user_info(current_user)


@router.put("/profile", response_model=UserInfo)
async def update_profile(payload: UserProfileUpdate, current_user: User = Depends(get_registered_user),
                         db: AsyncSession = Depends(get_db)):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip()
    await db.commit()
    return user_info(current_user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(rate_limit_user("password", 5, 900))])
async def change_password(payload: PasswordChange, request: Request, current_user: User = Depends(get_registered_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    validate_password_strength(payload.new_password, current_user.email)
    current_user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    await AuthService.revoke_all_sessions(db, current_user.id, except_session=request.state.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- MFA management ---
@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(current_user: User = Depends(get_registered_user), db: AsyncSession = Depends(get_db)):
    if current_user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA is already enabled.")
    secret = mfa.new_secret()
    current_user.mfa_secret = secret
    await db.commit()
    return MfaSetupResponse(secret=secret, otpauth_uri=mfa.provisioning_uri(secret, current_user.email))


@router.post("/mfa/enable", dependencies=[Depends(rate_limit_user("mfa_enable", 10, 300))])
async def mfa_enable(payload: MfaCode, request: Request, current_user: User = Depends(get_registered_user),
                     db: AsyncSession = Depends(get_db)):
    if current_user.mfa_enabled or not mfa.verify_totp(current_user.mfa_secret, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code.")
    codes, hashed = mfa.new_recovery_codes()
    current_user.mfa_enabled = True
    current_user.mfa_recovery_codes = hashed
    await db.commit()
    await AuthService.revoke_all_sessions(db, current_user.id, except_session=request.state.session_id)
    return {"recovery_codes": codes, "message": "MFA enabled. Store these recovery codes safely; they are shown once."}


@router.post("/mfa/disable", dependencies=[Depends(rate_limit_user("mfa_disable", 5, 900))])
async def mfa_disable(payload: MfaDisable, current_user: User = Depends(get_registered_user),
                      db: AsyncSession = Depends(get_db)):
    if not current_user.mfa_enabled or not verify_password(payload.password, current_user.hashed_password) \
            or not await AuthService.verify_second_factor(db, current_user, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid password or code.")
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_recovery_codes = None
    await db.commit()
    return {"message": "MFA disabled."}


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(rate_limit_user("account_delete", 3, 3600))])
async def delete_account(payload: AccountDelete, response: Response, current_user: User = Depends(get_registered_user),
                         db: AsyncSession = Depends(get_db)):
    """Deletes the user, their documents (files, chunks, vectors), chats and sessions."""
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password is incorrect.")
    from sqlalchemy import select
    refs = (await db.execute(select(Document.filepath).where(Document.user_id == current_user.id))).scalars().all()
    await db.delete(current_user)
    await db.commit()
    for ref in refs:
        storage.delete(ref)
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
