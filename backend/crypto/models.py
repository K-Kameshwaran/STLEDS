"""
File Overview:
This file defines the SQLAlchemy database model for Key Metadata.

Important Classes:
- `KeyMetadata`: Tracks cryptographic keys used for securing exam materials.
"""

from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from backend.database import Base

class KeyMetadata(Base):
    __tablename__ = "key_metadata"
    """
    KeyMetadata Model
    Tracks the metadata of the encryption keys used in the system without storing
    the actual key material directly in plaintext.
    """
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(String, unique=True, index=True, nullable=False) # e.g. AWS KMS Key ID or Alias
    purpose = Column(String, nullable=False) # e.g. "paper_encryption"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
