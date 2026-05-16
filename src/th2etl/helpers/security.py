from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext

from th2etl.configs.settings import get_settings

settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.encrypt_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
REFRESH_TOKEN_EXPIRE_DAYS = 7
AGENT_REFRESH_TOKEN_EXPIRE_DAYS = 90  


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token.

    NOTE: despite the historical name, this helper is used to mint tokens of
    several types (``access``, ``refresh``, ``download``). The ``type`` claim
    in ``data`` is preserved; if absent, it defaults to ``"access"``.

    Callers that want an access token can either omit ``type`` or pass
    ``type="access"`` explicitly. Callers minting a non-access token (e.g.
    the refresh cookie in ``auth/service.py``) MUST pass ``type`` explicitly
    — previously this function silently overwrote the field, producing
    "fake" access tokens that the refresh endpoint then rejected (B8 fix).
    """
    if not settings.encrypt_key:
        raise ValueError("Cannot create access token without an 'encrypt_key' set in the configuration.")

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)

    to_encode["exp"] = expire
    to_encode.setdefault("type", "access")
    encoded_jwt = jwt.encode(to_encode, settings.encrypt_key, algorithm=settings.jwt_algorithm)

    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token"""
    if not settings.encrypt_key:
        raise ValueError("Cannot create refresh token without an 'encrypt_key' set in the configuration.")

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.encrypt_key, algorithm=settings.jwt_algorithm)

    return encoded_jwt


def decode_access_token(token: str) -> Dict:
    """Decode and validate a JWT token"""
    if not settings.encrypt_key:
        raise ValueError("Cannot decode access token without an 'encrypt_key' set in the configuration.")

    try:
        payload = jwt.decode(token, settings.encrypt_key, algorithms=[settings.jwt_algorithm])

        # Verify token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_refresh_token(token: str) -> Dict:
    """Decode and validate a refresh token"""
    if not settings.encrypt_key:
        raise ValueError("Cannot decode refresh token without an 'encrypt_key' set in the configuration.")

    try:
        payload = jwt.decode(token, settings.encrypt_key, algorithms=[settings.jwt_algorithm])

        # Verify token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )


def create_agent_refresh_token(data: dict, expires_days: int = AGENT_REFRESH_TOKEN_EXPIRE_DAYS) -> str:
    """
    Create a refresh token for scheduled agent runs.
    """
    if not settings.encrypt_key:
        raise ValueError("Cannot create agent refresh token without an 'encrypt_key' set in the configuration.")

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)
    to_encode.update({"exp": expire, "type": "agent_refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.encrypt_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_agent_refresh_token(token: str) -> Dict:
    """
    Decode and validate an agent refresh token.

    """
    if not settings.encrypt_key:
        raise ValueError("Cannot decode agent refresh token without an 'encrypt_key' set in the configuration.")

    try:
        payload = jwt.decode(token, settings.encrypt_key, algorithms=[settings.jwt_algorithm])

        if payload.get("type") != "agent_refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected agent_refresh token.",
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent refresh token has expired. Please reschedule the agent run.",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate agent refresh token",
        )


def refresh_access_token_from_agent_refresh(refresh_token: str) -> str:
    """
    """
    # Decode and validate refresh token
    payload = decode_agent_refresh_token(refresh_token)

    # Extract data (excluding exp, type, iat)
    access_data = {k: v for k, v in payload.items() if k not in ["exp", "type", "iat"]}

    # Create fresh access token
    access_token = create_access_token(access_data)

    return access_token