import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qsl, unquote

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext

from backend.config import settings
from backend.database.connection import get_db

security = HTTPBearer()
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(password, hashed)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def validate_telegram_init_data(init_data: str) -> Optional[dict]:
    """Validate Telegram WebApp initData signature."""
    from loguru import logger
    try:
        # parse_qsl automatically URL-decodes values (required for correct HMAC)
        parsed = dict(parse_qsl(init_data, strict_parsing=False))

        received_hash = parsed.pop("hash", None)
        if not received_hash:
            logger.warning("validate_telegram_init_data: no hash field")
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        logger.debug(f"HMAC check: computed={computed_hash[:16]}... received={received_hash[:16]}... match={computed_hash == received_hash}")

        if not hmac.compare_digest(computed_hash, received_hash):
            logger.warning("validate_telegram_init_data: HMAC mismatch")
            return None

        user_data = parsed.get("user")
        if user_data:
            return json.loads(user_data)  # already URL-decoded by parse_qsl
        return {}
    except Exception as e:
        logger.error(f"validate_telegram_init_data exception: {e}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    from backend.database.models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не авторизован",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = verify_token(credentials.credentials)
    if not payload:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    from uuid import UUID as _UUID
    try:
        uid = _UUID(str(user_id))
    except (ValueError, AttributeError):
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == uid, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен. Требуются права администратора.",
        )
    return current_user


def encrypt_password(password: str) -> str:
    if not settings.ENCRYPTION_KEY:
        return password
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return f.encrypt(password.encode()).decode()
    except Exception:
        return password


def decrypt_password(encrypted: str) -> str:
    if not settings.ENCRYPTION_KEY:
        return encrypted
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        return encrypted
