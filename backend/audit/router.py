"""
File Overview:
Provides the REST API endpoints for accessing the Audit Log subsystem.

Important Functions:
- `verify_audit_log`: Endpoint to cryptographically verify the integrity of the audit log chain.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.users.models import User
from backend.auth.dependencies import require_permission
from backend.audit.service import verify_audit_chain

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/verify")
def verify_audit_log(
    db: Session = Depends(get_db),
    # Only Exam Controllers (or highly privileged auditors) can verify the chain
    current_user: User = Depends(require_permission("view_audit_data")) 
):
    """
    Verifies the deterministic hash chain of the audit log to detect tampering.
    """
    result = verify_audit_chain(db)
    return result
