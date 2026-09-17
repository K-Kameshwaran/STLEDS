"""
File Overview:
This file defines the SQLAlchemy database models for Release Sessions.

Important Classes:
- `ReleaseSession`: Represents a time-bound session during which papers are released.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.database import Base

class ReleaseSession(Base):
    __tablename__ = "release_sessions"
    """
    ReleaseSession Model
    Tracks the release of exam materials to specific centers.
    Day 5: Acts as the anchor for the Dual-Custodian Authorization workflow.
    """
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")
    started_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    shares = relationship("CustodianShare", back_populates="session")
    authorizations = relationship("ReleaseAuthorization", back_populates="session")

class CustodianShare(Base):
    __tablename__ = "custodian_shares"
    """
    CustodianShare Model
    Stores the KMS-encrypted XOR shares of the Key Encryption Key (KEK) for a specific session.
    Why it is required: Ensures that the key material is split and protected. Neither share
    alone can reconstruct the KEK.
    """
    id = Column(Integer, primary_key=True, index=True)
    release_session_id = Column(Integer, ForeignKey("release_sessions.id"), nullable=False)
    role_name = Column(String, nullable=False) # 'EXAM_CONTROLLER' or 'EXTERNAL_OBSERVER'
    kms_encrypted_share = Column(String, nullable=False) # Base64 encoded KMS ciphertext
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    session = relationship("ReleaseSession", back_populates="shares")

class ReleaseAuthorization(Base):
    __tablename__ = "release_authorizations"
    """
    ReleaseAuthorization Model
    Tracks an individual custodian's explicit authorization for a release.
    Why it is required: Implements Replay Protection by binding the auth to a specific exam,
    session, and user, and utilizing a 'consumed' flag to prevent reuse.
    """
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    release_session_id = Column(Integer, ForeignKey("release_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Replay Protection tracking
    client_timestamp = Column(DateTime, nullable=False)
    server_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    consumed = Column(Boolean, default=False, nullable=False)
    
    session = relationship("ReleaseSession", back_populates="authorizations")
