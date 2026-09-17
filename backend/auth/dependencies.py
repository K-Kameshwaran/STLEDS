"""
File Overview:
This file defines FastAPI dependencies used to secure endpoints.

Important Functions:
- `get_current_user`: Validates the JWT and returns the current user identity.
- `require_role`: A dependency factory that ensures the user has a specific role.

Why it is required:
These dependencies ensure that protected backend functionality can only be
accessed by authenticated, active users with the correct roles.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.users.models import User, Role
from backend.auth.schemas import TokenData
from backend.auth.security import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Validates the provided JWT token.
    Raises 401 Unauthorized if the token is invalid, expired, or the user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email, role=role)
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    # Check simple revocation strategy (e.g., if token is expired, JWTError is raised above)
    # If we wanted to check a blocklist, we would query the database here.
    return user

from backend.auth.rbac import has_permission
from backend.exams.models import Paper, ExamCenter

def require_permission(required_permission: str):
    """
    Dependency factory to enforce role-based access control (RBAC) via permissions.
    Why it is required: Authentication checks *who* the user is. This checks *what*
    their role is allowed to do, preventing users from executing routes they lack permissions for.
    """
    def permission_checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        role = db.query(Role).filter(Role.id == current_user.role_id).first()
        role_name = role.name if role else "UNKNOWN"
        
        if not has_permission(role_name, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions for this action"
            )
        return current_user
    return permission_checker

def get_paper_with_object_auth(paper_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Paper:
    """
    Object-Level Authorization: Fetches a paper and verifies the user's specific access rights to it.
    
    Why it is required: A Center Superintendent might have the 'DOWNLOAD_ASSIGNED_PAPER' permission,
    but they should ONLY be able to download papers assigned to THEIR center. We must check
    this server-side, ignoring any `center_id` claims passed by the client in the request payload.
    """
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    role = db.query(Role).filter(Role.id == current_user.role_id).first()
    role_name = role.name if role else "UNKNOWN"
    
    # 1. If Center Superintendent, ensure their center is assigned to this exam
    if role_name == "CENTER_SUPERINTENDENT":
        if not current_user.center_id:
            raise HTTPException(status_code=403, detail="User is not assigned to a center")
            
        assignment = db.query(ExamCenter).filter(
            ExamCenter.exam_id == paper.exam_id,
            ExamCenter.center_id == current_user.center_id
        ).first()
        
        if not assignment:
            # The exam (and thus paper) is not assigned to this user's center. DENY.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Object access denied: Paper not assigned to your center"
            )
            
    # 2. If Question Setter, ensure they are the creator of this paper
    elif role_name == "QUESTION_SETTER":
        if paper.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Object access denied: You do not own this paper"
            )
            
    # Other roles (like Exam Controller) might have global access, handled implicitly if they pass the permission check above.
    
    return paper

