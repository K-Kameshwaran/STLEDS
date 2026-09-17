"""
File Overview:
Defines the `AuditLog` database model for securely recording important system events.

Important Classes:
- `AuditLog`: Represents a single tamper-evident audit record in the database.

Why it is needed:
Audit trails are required for forensic accountability. The `previous_hash` and 
`current_hash` fields create a cryptographic chain. If an attacker manually alters a historical 
record in the database, the hash for that record and all subsequent records will become invalid,
detecting the tamper.
"""
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from backend.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    """
    AuditLog Model
    Stores deterministic, chronologically chained event records.
    """
    id = Column(Integer, primary_key=True, index=True)
    
    # We enforce UTC for all timestamps
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Nullable because some events (like failed login attempts by an unknown user) might lack a known actor
    actor_id = Column(Integer, nullable=True)
    
    action = Column(String, nullable=False) # e.g., 'LOGIN_SUCCESS', 'DOWNLOAD'
    
    exam_id = Column(Integer, nullable=True)
    resource_id = Column(Integer, nullable=True) # e.g., paper_id
    
    result = Column(String, nullable=False) # 'SUCCESS', 'FAILURE'
    
    metadata_json = Column(String, nullable=True) # JSON-serialized additional context
    
    # Hash Chaining
    previous_hash = Column(String, nullable=False)
    current_hash = Column(String, nullable=False)
