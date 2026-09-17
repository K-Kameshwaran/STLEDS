"""
File Overview:
This file handles cryptographic operations related to passwords and tokens.

Important Functions:
- `verify_password`: Compares a plaintext password against a stored bcrypt hash.
- `get_password_hash`: Generates a bcrypt hash for a new plaintext password.
- `create_access_token`: Generates a JWT (JSON Web Token) for authentication.

Why it is required:
Passwords must never be stored in plaintext. Passlib handles bcrypt hashing securely.
JWTs allow stateless, scalable authentication sessions.
"""

from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt
import os
import warnings

# Secret key for JWT signing. In production, this must be a strong secret.
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if os.getenv("ENV") == "production":
        raise RuntimeError("FATAL: JWT_SECRET environment variable is missing in production!")
    warnings.warn("Using unsafe development JWT_SECRET. Do not use in production.")
    SECRET_KEY = "supersecret_dev_key"
else:
    SECRET_KEY = JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Initialize Passlib with bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies that a plain password matches the hashed password.
    Returns True if match, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Hashes a password using bcrypt.
    """
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Creates a JWT access token.
    `data` typically contains the user subject ('sub': user.email) and roles.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
