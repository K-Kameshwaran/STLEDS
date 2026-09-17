"""
File Overview:
This file defines the Pydantic models (schemas) used for Authentication API requests and responses.

Why it is required:
Pydantic ensures data validation for incoming requests and formats outgoing responses.
"""
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str
    mfa_required: bool = False

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: Optional[str] = None
