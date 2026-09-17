"""
File Overview:
Implements the core business logic for deterministic audit logging and cryptographic verification.

Important Functions:
- `create_audit_record`: Safely creates a chained audit record.
- `verify_audit_chain`: Re-calculates and validates the entire audit chain to detect tampering.
- `_canonicalize_record`: Deterministically serializes fields into a strictly ordered string.

Why it is required:
A standard database log can be modified by an administrator. By cryptographically chaining 
each record to the previous one (current_hash = SHA256(previous_hash + canonical_data)), 
any modification of historical records becomes mathematically obvious during verification.
"""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import asc
from typing import Optional, Dict, Any, Tuple

from backend.audit.models import AuditLog

# The starting hash for the first record in the database
GENESIS_HASH = hashlib.sha256(b"GENESIS").hexdigest()

def _canonicalize_record(
    timestamp: datetime, 
    actor_id: Optional[int], 
    action: str, 
    exam_id: Optional[int], 
    resource_id: Optional[int], 
    result: str, 
    metadata_json: Optional[str]
) -> str:
    """
    Deterministic serialization of the audit fields.
    Ordering and string casting must NEVER change, otherwise historical hashes will fail.
    Null values are represented as empty strings to maintain strict deterministic structure.
    """
    # Ensure timestamp is normalized to ISO 8601 format in UTC
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    ts_str = timestamp.isoformat()
    
    actor_str = str(actor_id) if actor_id is not None else ""
    action_str = str(action)
    exam_str = str(exam_id) if exam_id is not None else ""
    resource_str = str(resource_id) if resource_id is not None else ""
    result_str = str(result)
    meta_str = str(metadata_json) if metadata_json is not None else ""
    
    # Pipe delimited deterministic string
    canonical = f"{ts_str}|{actor_str}|{action_str}|{exam_str}|{resource_str}|{result_str}|{meta_str}"
    return canonical

def create_audit_record(
    db: Session,
    action: str,
    result: str,
    actor_id: Optional[int] = None,
    exam_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> AuditLog:
    """
    Safely creates a chained audit record. 
    Retrieves the previous hash, canonicalizes data, and computes the current hash.
    """
    metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
    
    # We must lock the table or carefully fetch the very last record to avoid race conditions.
    # In this prototype, we rely on standard sequential insertion.
    last_record = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    
    previous_hash = last_record.current_hash if last_record else GENESIS_HASH
    
    timestamp = datetime.now(timezone.utc)
    
    canonical_data = _canonicalize_record(
        timestamp=timestamp,
        actor_id=actor_id,
        action=action,
        exam_id=exam_id,
        resource_id=resource_id,
        result=result,
        metadata_json=metadata_json
    )
    
    hash_input = previous_hash + canonical_data
    current_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
    
    new_record = AuditLog(
        timestamp=timestamp,
        actor_id=actor_id,
        action=action,
        exam_id=exam_id,
        resource_id=resource_id,
        result=result,
        metadata_json=metadata_json,
        previous_hash=previous_hash,
        current_hash=current_hash
    )
    
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

def verify_audit_chain(db: Session) -> dict:
    """
    Reads the entire audit chain in ID order, recalculates expected hashes, 
    and verifies that the mathematical chain remains intact.
    
    Returns a dict with 'valid' (bool) and 'first_invalid_record' (int or None).
    """
    records = db.query(AuditLog).order_by(asc(AuditLog.id)).all()
    
    expected_previous_hash = GENESIS_HASH
    
    for record in records:
        # Check linkage
        if record.previous_hash != expected_previous_hash:
            return {"valid": False, "first_invalid_record": record.id}
            
        # Recompute current hash
        canonical_data = _canonicalize_record(
            timestamp=record.timestamp,
            actor_id=record.actor_id,
            action=record.action,
            exam_id=record.exam_id,
            resource_id=record.resource_id,
            result=record.result,
            metadata_json=record.metadata_json
        )
        hash_input = record.previous_hash + canonical_data
        expected_current_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        
        if record.current_hash != expected_current_hash:
            return {"valid": False, "first_invalid_record": record.id}
            
        # Move forward
        expected_previous_hash = record.current_hash
        
    return {"valid": True, "first_invalid_record": None}
