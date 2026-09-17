"""
File Overview:
This file defines the SQLAlchemy database models for Users and Roles.

Important Classes:
- `Role`: Represents the different system roles (e.g., QUESTION_SETTER).
- `User`: Represents a system user, containing authentication and identity info.

Design Decisions:
We separated the User and Role models so that roles can be dynamically managed
and referenced, fulfilling the Day 2 requirement for a relational role structure.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.database import Base

class Role(Base):
    __tablename__ = "roles"
    """
    Role Model
    Why it is needed: Maps to the `roles` table. By storing roles in a separate table,
    we ensure normalization and the ability to easily add new roles in the future without
    altering the users table structure.
    """
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    """
    User Model
    Why it is needed: The core identity model holding secure authentication data.
    Notice that we store `password_hash` instead of plaintext passwords.
    `totp_secret` is used for High-Privilege Multi-Factor Authentication (MFA).
    """
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False) # Used as username
    password_hash = Column(String, nullable=False)
    
    # Foreign Key to Roles
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    role = relationship("Role", back_populates="users")
    
    center_id = Column(Integer, nullable=True) # Used if user belongs to a specific center
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # MFA
    totp_secret = Column(String, nullable=True) # Base32 secret for TOTP
