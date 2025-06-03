# app/services/auth_service.py

import os
from datetime import datetime, timedelta, timezone # Use timezone-aware datetime
from typing import Optional, Union

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.models import UserRole 

# Local imports
from app import models, database

load_dotenv() # Load environment variables from .env

# --- Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY", "dnfifjn4205fjv")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

if not SECRET_KEY:
    raise ValueError("Missing SECRET_KEY environment variable")

# --- Password Hashing Context ---
# Should match the one in models.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- OAuth2 Scheme ---
# tokenUrl points to the endpoint that issues the token (in auth.py)
# auto_error=False makes it optional for the get_optional_current_user dependency
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=True) # Requires token for get_current_user
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False) # Optional for checking login status

# --- Helper Functions ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Database Interaction ---
def get_user(db: Session, username_or_email: str) -> Optional[models.User]:
    """Retrieves a user by username or email."""
    return db.query(models.User).filter(
        (models.User.username == username_or_email) | (models.User.email == username_or_email)
    ).first()

# --- Authentication Logic ---
def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    """Authenticates a user by username/email and password."""
    user = get_user(db, username)
    if not user:
        return None # User not found
    if not user.is_active:
        return None # User is inactive
    if not verify_password(password, user.hashed_password):
        return None # Incorrect password
    return user

# --- Dependencies ---
async def get_current_user_from_token(
    token: Optional[str], db: Session
) -> Optional[models.User]:
    """Helper to decode token and get user, returns None on any error."""
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            return None # No username ('sub') in token
        # Optional: Check token expiry explicitly if needed, though decode usually handles it
        # token_expires = payload.get("exp")
        # if token_expires is None or datetime.now(timezone.utc) > datetime.fromtimestamp(token_expires, tz=timezone.utc):
        #      return None # Token expired

    except JWTError:
        return None # Invalid token (decode failed)

    user = get_user(db, username_or_email=username)
    if user is None or not user.is_active:
        return None # User not found in DB or inactive

    return user

async def get_optional_current_user(
    request: Request,
    db: Session = Depends(database.get_db),
    token_header: Optional[str] = Depends(optional_oauth2_scheme) # Check header first
) -> Optional[models.User]:
    """
    Dependency: Gets the current user from token (header OR cookie) if available.
    Returns User object or None. Does NOT raise HTTP 401.
    """
    token = token_header
    # Check for token in HttpOnly cookie if not in header
    if not token:
        token = request.cookies.get("access_token") # Adjust cookie name if needed

    return await get_current_user_from_token(token, db)


async def get_current_user(
    request: Request,
    db: Session = Depends(database.get_db),
    # Use the *required* scheme here or manually check cookie/header
    # Using the required scheme only works easily for header auth
    # We'll manually check header/cookie and raise error
    # token_header: Optional[str] = Depends(oauth2_scheme) # Original way
) -> models.User:
    """
    Dependency: Gets the current active user from token (header OR cookie).
    Raises HTTP 401 if not authenticated or inactive.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}, # Or appropriate header if using cookies mainly
    )
    # Manually check header first, then cookie
    token = request.headers.get("Authorization")
    if token and token.startswith("Bearer "):
        token = token.split("Bearer ")[1]
    else:
        token = request.cookies.get("access_token") # Check cookie

    if not token:
        raise credentials_exception # No token found

    user = await get_current_user_from_token(token, db)
    if user is None:
        raise credentials_exception # Token invalid, expired, or user not found/inactive

    return user

async def get_current_active_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Dependency: Ensures the current user is an active Admin."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user


async def get_current_active_instructor(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Dependency: Ensures the current user is an active Instructor."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Instructor privileges required."
        )
    if not current_user.is_active:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive."
        )
    return current_user
    
async def get_current_active_student(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Dependency: Ensures the current user is an active Student."""
    if current_user.role != UserRole.STUDENT:
        # Redirect to login or show generic unauthorized? Redirect is often better UX.
        # For simplicity, raising 403 here. Consider redirecting from the route instead.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Student privileges required."
        )
    if not current_user.is_active:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive."
        )
    # Optional: Check if student_profile exists if needed immediately
    # if not current_user.student_profile:
    #     raise HTTPException(status_code=404, detail="Student profile not found for this user.")
    return current_user