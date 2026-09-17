"""
File Overview:
This file implements the API endpoints for Exam and Paper workflows.

Important Functions:
- `create_paper`: Allows a QUESTION_SETTER to upload a paper. Handles AES-256-GCM encryption and simulated R2 storage.
- `download_paper`: Allows authorized users to download a paper. Retrieves ciphertext from simulated R2, verifies integrity, and decrypts.

Why it is required:
Encryption MUST happen before permanent storage. We read the file in memory, encrypt it, upload the ciphertext
to the private R2 bucket, and save the metadata/wrapped keys in the database.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
import hashlib
import json

from backend.database import get_db
from backend.users.models import User
from backend.exams.models import Paper, Exam
from backend.auth.dependencies import get_current_user, require_permission, get_paper_with_object_auth
from backend.crypto.engine import generate_key, generate_nonce, encrypt_document, decrypt_document
from backend.crypto.kms import wrap_key, unwrap_key
from backend.storage.r2 import upload_object, download_object
from backend.audit.service import create_audit_record

router = APIRouter(prefix="/exams", tags=["exams"])

@router.post("/papers", status_code=status.HTTP_201_CREATED)
def create_paper(
    title: str = Form(...),
    exam_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    # 1. Auth & 2. Role (RBAC) Check
    current_user: User = Depends(require_permission("upload_paper"))
):
    """
    Creates a new paper record. Only QUESTION_SETTER can access this.
    Pipeline: Validation -> Gen DEK -> Encrypt -> Upload Ciphertext -> Save Metadata
    """
    # Step 1: Input Validation
    if not file:
        create_audit_record(db, "UPLOAD", "FAILURE", actor_id=current_user.id, metadata={"reason": "File is missing"})
        raise HTTPException(status_code=400, detail="File is missing")
        
    # Day 8: File Size Limit (20MB)
    MAX_FILE_SIZE = 20 * 1024 * 1024
    
    plaintext = file.file.read()
    
    if len(plaintext) > MAX_FILE_SIZE:
        create_audit_record(db, "UPLOAD", "FAILURE", actor_id=current_user.id, metadata={"reason": "File too large"})
        raise HTTPException(status_code=400, detail="File exceeds maximum allowed size (20MB)")
        
    # Day 8: File Type Validation (Magic Bytes for PDF)
    # Checking the first 4 bytes for '%PDF' signature rather than relying on filename
    if not plaintext.startswith(b"%PDF"):
        create_audit_record(db, "UPLOAD", "FAILURE", actor_id=current_user.id, metadata={"reason": "Invalid file type. Must be a real PDF."})
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are allowed.")
        
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        create_audit_record(db, "UPLOAD", "FAILURE", actor_id=current_user.id, metadata={"reason": "Exam not found", "exam_id": exam_id})
        raise HTTPException(status_code=404, detail="Exam not found")
        
    document_hash = hashlib.sha256(plaintext).hexdigest()
    
    # Step 3: Generate DEK & Nonce
    dek = generate_key()
    nonce = generate_nonce()
    
    # Step 4: AES-256-GCM Encryption
    ciphertext = encrypt_document(plaintext, dek, nonce)
    plaintext = b""
    
    # Step 5: Upload Ciphertext to R2
    storage_object_id = upload_object(ciphertext)
    
    # Step 6: Split the DEK (Two-Party Authorization setup)
    from backend.crypto.splitting import split_key
    from backend.crypto.kms_client import kms_encrypt
    
    share_a, share_b = split_key(dek)
    
    # Encrypt the shares using AWS KMS
    kms_share_a = kms_encrypt(share_a)
    kms_share_b = kms_encrypt(share_b)
    
    encryption_metadata = {
        "kms_share_a": kms_share_a,
        "kms_share_b": kms_share_b,
        "document_nonce_b64": nonce.hex()
    }
    
    from backend.release.state_machine import PaperState
    
    paper = Paper(
        title=title,
        exam_id=exam_id,
        storage_object_id=storage_object_id,
        status=PaperState.ENCRYPTED,
        created_by=current_user.id,
        document_hash=document_hash,
        encryption_metadata=json.dumps(encryption_metadata)
    )
    
    db.add(paper)
    db.commit()
    db.refresh(paper)
    
    create_audit_record(db, "UPLOAD", "SUCCESS", actor_id=current_user.id, exam_id=exam_id, resource_id=paper.id)
    
    return {"message": "Paper encrypted and uploaded successfully", "paper_id": paper.id}

@router.post("/papers/{paper_id}/status")
def change_paper_status(
    paper_id: int,
    new_status: str,
    db: Session = Depends(get_db),
    # In a real app, permissions would be tighter per-transition. 
    current_user: User = Depends(get_current_user)
):
    """
    Enforces server-side state transitions. 
    Clients cannot force arbitrary states (e.g., RELEASED).
    """
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    from backend.release.state_machine import can_transition, get_effective_state, PaperState
    
    current_state = get_effective_state(paper, paper.exam)
    
    if not can_transition(current_state, new_status):
        create_audit_record(db, "STATUS_CHANGE", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"from": current_state, "to": new_status.upper()})
        raise HTTPException(status_code=400, detail=f"Invalid transition from {current_state} to {new_status.upper()}")
        
    paper.status = new_status.upper()
    db.commit()
    
    # Audit log the specific transition if it's a critical review/approval action
    if new_status.upper() == PaperState.PENDING_REVIEW:
        create_audit_record(db, "REVIEW", "SUCCESS", actor_id=current_user.id, resource_id=paper.id)
    elif new_status.upper() == PaperState.APPROVED:
        create_audit_record(db, "APPROVAL", "SUCCESS", actor_id=current_user.id, resource_id=paper.id)
    else:
        create_audit_record(db, "STATUS_CHANGE", "SUCCESS", actor_id=current_user.id, resource_id=paper.id, metadata={"new_status": new_status.upper()})
    
    return {"message": f"Status updated to {paper.status}"}


@router.get("/papers/{paper_id}/download")
def download_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    # 1. Auth & 2. Role Check (must have permission to download)
    current_user: User = Depends(require_permission("download_assigned_paper")),
    # 3. Object-Level Auth Check
    paper: Paper = Depends(get_paper_with_object_auth)
):
    """
    ATOMIC RELEASE DECISION:
    Enforces all 6 conditions before releasing the plaintext. Fails closed.
    """
    if not paper.encryption_metadata or not paper.storage_object_id:
        raise HTTPException(status_code=500, detail="Paper metadata is incomplete")
        
    from backend.release.state_machine import get_effective_state, PaperState
    from backend.release.timing import evaluate_time_state, TimeState
    from backend.release.models import ReleaseSession
    
    # CONDITION 1 & 2: Paper Approval & Release Window Validation
    # get_effective_state natively validates that Server UTC Time is within release_start & release_end
    effective_state = get_effective_state(paper, paper.exam)
    if effective_state not in [PaperState.RELEASE_WINDOW, PaperState.RELEASED]:
        create_audit_record(db, "RELEASE_DENIED", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"reason": "Not in RELEASE_WINDOW or RELEASED", "state": effective_state})
        # If Before Window, it returns LOCKED. If After, EXPIRED. If unapproved, PENDING_REVIEW etc.
        raise HTTPException(
            status_code=403, 
            detail=f"Release Denied: Paper is not in RELEASE_WINDOW state. Current state: {effective_state}"
        )
        
    # CONDITION 3 & 4: Controller & External Observer Authorization
    session = db.query(ReleaseSession).filter(ReleaseSession.exam_id == paper.exam_id).first()
    if not session or session.status != "active":
        create_audit_record(db, "UNAUTHORIZED_ACCESS", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"reason": "Dual custodian authorization missing"})
        raise HTTPException(status_code=403, detail="Release Denied: Dual-custodian authorization missing or incomplete.")
        
    try:
        # Step 1: Download Ciphertext
        ciphertext = download_object(paper.storage_object_id)
        
        # Step 2: Extract Metadata
        meta = json.loads(paper.encryption_metadata)
        kms_share_a = meta["kms_share_a"]
        kms_share_b = meta["kms_share_b"]
        document_nonce = bytes.fromhex(meta["document_nonce_b64"])
        
        # CONDITION 6: Key Authorization (AWS KMS)
        from backend.crypto.kms_client import kms_decrypt
        share_a = kms_decrypt(kms_share_a)
        share_b = kms_decrypt(kms_share_b)
        
        # Reconstruct the DEK via XOR Splitting
        from backend.crypto.splitting import reconstruct_key
        dek = reconstruct_key(share_a, share_b)
        
        # CONDITION 5: Paper Integrity Verified
        # If the file was tampered with in R2, this will raise ValueError
        plaintext = decrypt_document(ciphertext, dek, document_nonce)
        
        # CONDITION 7: Dynamic Forensic Watermarking
        # Identity parameters are extracted strictly from the trusted server-side context.
        # We DO NOT trust any client-supplied center ID, role, or timestamp.
        from backend.crypto.watermark import apply_watermark
        from datetime import datetime, timezone
        
        try:
            watermarked_pdf = apply_watermark(
                pdf_bytes=plaintext,
                exam_id=paper.exam_id,
                center_id=current_user.center_id,
                user_id=current_user.id,
                timestamp=datetime.now(timezone.utc)
            )
        except ValueError as e:
            # If the watermark fails (e.g., uploaded file wasn't a valid PDF)
            raise HTTPException(status_code=500, detail="Failed to generate secure individualized document.")
            
        # Secure memory cleanup: wipe the original plaintext reference early
        plaintext = b""
        
        # ALL CONDITIONS MET: ATOMIC RELEASE SUCCESS
        # Optional: Transition paper state to RELEASED upon successful delivery
        if paper.status != PaperState.RELEASED:
            paper.status = PaperState.RELEASED
            db.commit()
            
        # Return the watermarked copy securely over HTTPS
        create_audit_record(db, "DOWNLOAD", "SUCCESS", actor_id=current_user.id, resource_id=paper.id)
        return Response(content=watermarked_pdf, media_type="application/pdf")
        
    except ValueError as e:
        # CONDITION 5 FAILED
        create_audit_record(db, "INTEGRITY_FAILURE", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"reason": "Tampered/Corrupted Document"})
        raise HTTPException(status_code=500, detail="Release Denied: Integrity check failed. Document corrupted or tampered.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        # Generic safe failure for KMS or other unexpected issues
        create_audit_record(db, "UNAUTHORIZED_ACCESS", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"reason": "Key authorization or secure delivery failed."})
        raise HTTPException(status_code=500, detail=f"Release Denied: Key authorization or secure delivery failed. Error: {repr(e)}")

@router.get("/papers/{paper_id}/view")
def view_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    # 1. Auth & 2. Role Check (must have permission to review)
    current_user: User = Depends(require_permission("review_paper"))
):
    """
    Allows a Reviewer to view the document securely in-browser.
    Strictly segregated from the download workflow.
    """
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    if not paper.encryption_metadata or not paper.storage_object_id:
        raise HTTPException(status_code=500, detail="Paper metadata is incomplete")
        
    try:
        # Step 1: Download Ciphertext
        ciphertext = download_object(paper.storage_object_id)
        
        # Step 2: Extract Metadata
        meta = json.loads(paper.encryption_metadata)
        kms_share_a = meta["kms_share_a"]
        kms_share_b = meta["kms_share_b"]
        document_nonce = bytes.fromhex(meta["document_nonce_b64"])
        
        # Step 3: Key Authorization (AWS KMS)
        from backend.crypto.kms_client import kms_decrypt
        share_a = kms_decrypt(kms_share_a)
        share_b = kms_decrypt(kms_share_b)
        
        # Reconstruct the DEK via XOR Splitting
        from backend.crypto.splitting import reconstruct_key
        dek = reconstruct_key(share_a, share_b)
        
        # Step 4: Paper Integrity Verified
        plaintext = decrypt_document(ciphertext, dek, document_nonce)
        
        # Log view action
        create_audit_record(db, "VIEW_PAPER", "SUCCESS", actor_id=current_user.id, resource_id=paper.id)
        
        # Return inline for browser rendering (no download)
        headers = {
            "Content-Disposition": "inline; filename=preview.pdf",
            "X-Content-Type-Options": "nosniff"
        }
        return Response(content=plaintext, media_type="application/pdf", headers=headers)
        
    except ValueError as e:
        create_audit_record(db, "INTEGRITY_FAILURE", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"reason": "Tampered/Corrupted Document"})
        raise HTTPException(status_code=500, detail="View Denied: Integrity check failed. Document corrupted or tampered.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
        create_audit_record(db, "UNAUTHORIZED_ACCESS", "FAILURE", actor_id=current_user.id, resource_id=paper.id, metadata={"reason": "Key authorization failed."})
        raise HTTPException(status_code=500, detail="View Denied: Key authorization failed.")

