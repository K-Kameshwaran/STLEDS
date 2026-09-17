"""
File Overview:
This file implements the Dual-Custodian Authorization workflow API routes.

Important Functions:
- `create_release_session`: Initializes a release window for an exam.
- `authorize_release_session`: Allows a custodian (Controller/Observer) to submit their authorization share.
- `execute_release_session`: Evaluates the submitted authorizations. If both valid custodians have authorized, it marks the session as 'released'.

Why it is required:
A single actor (even a super admin) must NEVER be able to release the question papers alone.
By forcing two distinct identities (Controller + Observer) to authorize the specific session,
we enforce separation of authorization responsibilities.

Replay Protection:
Authorizations are tightly bound to `exam_id`, `release_session_id`, and `user_id`.
They include a client timestamp to prevent stale requests, and a `consumed` flag
to ensure an authorization cannot be reused for a different lifecycle event.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List
from pydantic import BaseModel

from backend.database import get_db
from backend.users.models import User
from backend.exams.models import Exam
from backend.release.models import ReleaseSession, ReleaseAuthorization
from backend.auth.dependencies import get_current_user
from backend.audit.service import create_audit_record

router = APIRouter(prefix="/release/sessions", tags=["release"])

class ReleaseSessionCreate(BaseModel):
    exam_id: int

class AuthorizationSubmit(BaseModel):
    client_timestamp: datetime

@router.post("", status_code=status.HTTP_201_CREATED)
def create_release_session(
    request: ReleaseSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Creates a new release session for an exam.
    Any authenticated user can request to start a session, but it requires
    dual-authorization to actually activate.
    """
    if current_user.role.name not in ["EXAM_CONTROLLER", "EXTERNAL_OBSERVER"]:
        raise HTTPException(status_code=403, detail="Not authorized to create release session")

    exam = db.query(Exam).filter(Exam.id == request.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
        
    session = ReleaseSession(
        exam_id=request.exam_id,
        status="pending",
        started_at=datetime.now(timezone.utc)
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"message": "Release session created", "session_id": session.id}

@router.post("/{session_id}/authorize")
def authorize_release_session(
    session_id: int,
    request: AuthorizationSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submits a custodian's authorization for the release session.
    Security Check: Only EXAM_CONTROLLER (Custodian A) and EXTERNAL_OBSERVER (Custodian B) can authorize.
    """
    session = db.query(ReleaseSession).filter(ReleaseSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.status != "pending":
        raise HTTPException(status_code=400, detail="Session is not pending authorization")
        
    role_name = current_user.role.name
    if role_name not in ["EXAM_CONTROLLER", "EXTERNAL_OBSERVER"]:
        raise HTTPException(status_code=403, detail="Role not authorized to act as a custodian")
        
    # Replay Protection: Time window validation (e.g., must be within last 5 minutes)
    now = datetime.now(timezone.utc)
    if now - request.client_timestamp > timedelta(minutes=5) or request.client_timestamp > now + timedelta(minutes=1):
        raise HTTPException(status_code=400, detail="Authorization timestamp is stale or invalid")
        
    # Replay Protection: Prevent duplicate active authorizations by the same user for this session
    existing_auth = db.query(ReleaseAuthorization).filter(
        ReleaseAuthorization.release_session_id == session_id,
        ReleaseAuthorization.user_id == current_user.id,
        ReleaseAuthorization.consumed == False
    ).first()
    
    if existing_auth:
        raise HTTPException(status_code=400, detail="Active authorization already exists")
        
    auth = ReleaseAuthorization(
        exam_id=session.exam_id,
        release_session_id=session.id,
        user_id=current_user.id,
        client_timestamp=request.client_timestamp
    )
    db.add(auth)
    db.flush()
    
    # Determine if both required roles have authorized
    authorizations = db.query(ReleaseAuthorization).filter(
        ReleaseAuthorization.release_session_id == session_id,
        ReleaseAuthorization.consumed == False
    ).all()
    
    authorized_roles = set()
    for active_auth in authorizations:
        u = db.query(User).filter(User.id == active_auth.user_id).first()
        if u:
            authorized_roles.add(u.role.name)
    
    if "EXAM_CONTROLLER" in authorized_roles and "EXTERNAL_OBSERVER" in authorized_roles:
        session.status = "ready"
        create_audit_record(db, "RELEASE_AUTHORIZED", "SUCCESS", actor_id=current_user.id, exam_id=session.exam_id)
        
    db.commit()
    
    return {"message": "Authorization successful"}

@router.post("/{session_id}/execute")
def execute_release_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Evaluates the authorizations. If both Custodian A and B have provided valid,
    unconsumed authorizations, the session transitions to 'active', allowing
    Center Superintendents to download papers.
    """
    session = db.query(ReleaseSession).filter(ReleaseSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.status not in ["pending", "ready"]:
        raise HTTPException(status_code=400, detail="Session is already executed or closed")
        
    # Fetch all unconsumed authorizations for this session
    auths = db.query(ReleaseAuthorization).filter(
        ReleaseAuthorization.release_session_id == session_id,
        ReleaseAuthorization.consumed == False
    ).all()
    
    # We need exactly two distinct roles: EXAM_CONTROLLER and EXTERNAL_OBSERVER
    authorized_roles = set()
    valid_auths = []
    
    for auth in auths:
        # Resolve user role
        user = db.query(User).filter(User.id == auth.user_id).first()
        if user and user.role.name in ["EXAM_CONTROLLER", "EXTERNAL_OBSERVER"]:
            authorized_roles.add(user.role.name)
            valid_auths.append(auth)
            
    if "EXAM_CONTROLLER" not in authorized_roles or "EXTERNAL_OBSERVER" not in authorized_roles:
        # Fails closed. Do not specify WHICH one is missing to prevent reconnaissance.
        raise HTTPException(status_code=403, detail="Insufficient custodian authorization material.")
        
    # Both custodians are present. Consume the authorizations (Replay Protection)
    for auth in valid_auths:
        auth.consumed = True
        
    session.status = "active"
    db.commit()
    
    create_audit_record(db, "RELEASE_ATTEMPT", "SUCCESS", actor_id=current_user.id, exam_id=session.exam_id)
    
    return {"message": "Release session activated successfully. Both custodians validated."}
