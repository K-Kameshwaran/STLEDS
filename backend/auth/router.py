"""
File Overview:
This file implements the API endpoints for Authentication, including login and token validation.

Important Functions:
- `login`: Authenticates the user, verifies passwords and active status, checks MFA if required, and returns a JWT.

Design Decisions:
We chose to implement MFA verification in the same login flow for simplicity during Day 2,
meaning if a user requires MFA, they must supply `mfa_code` in the `LoginRequest`.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.users.models import User, Role
from backend.auth.schemas import LoginRequest, Token
from backend.auth.security import verify_password, create_access_token
from backend.auth.mfa import MFA_REQUIRED_ROLES, verify_totp
from backend.audit.service import create_audit_record
from backend.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint.
    1. Identifies the user by email.
    2. Verifies the password securely.
    3. Checks if the account is active.
    4. Enforces MFA for high-privilege roles.
    5. Returns a JWT access token on success.
    """
    user = db.query(User).filter(User.email == login_data.email).first()
    
    # 1 & 2. Verify identity and password
    # We use a generic error message to prevent enumeration attacks.
    if not user or not verify_password(login_data.password, user.password_hash):
        if user:
            # Audit failed login for known user
            create_audit_record(db, action="LOGIN_FAILURE", result="FAILURE", actor_id=user.id)
        else:
            # Audit failed login attempt for unknown user
            create_audit_record(db, action="LOGIN_FAILURE", result="FAILURE", metadata={"email": login_data.email})
            
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # 3. Check active status
    if not user.is_active:
        create_audit_record(db, action="LOGIN_FAILURE", result="FAILURE", actor_id=user.id, metadata={"reason": "inactive"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )
        
    role = db.query(Role).filter(Role.id == user.role_id).first()
    role_name = role.name if role else "UNKNOWN"
    
    # 4. Enforce MFA if required
    if role_name in MFA_REQUIRED_ROLES:
        if not login_data.mfa_code:
            # Tell the client that MFA is required
            return Token(access_token="", token_type="bearer", mfa_required=True)
            
        if not user.totp_secret or not verify_totp(user.totp_secret, login_data.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code"
            )

    # 5. Create JWT
    access_token = create_access_token(
        data={"sub": user.email, "role": role_name}
    )
    
    return Token(access_token=access_token, token_type="bearer", mfa_required=False)
