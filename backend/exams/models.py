"""
File Overview:
This file defines the SQLAlchemy database models for Exams, Papers, and Approvals.

Important Classes:
- `Exam`: Represents a specific examination event.
- `Paper`: Represents a specific question paper associated with an Exam.
- `Approval`: Represents the approval workflow for a paper.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.database import Base

class ExamCenter(Base):
    __tablename__ = "exam_centers"
    """
    Association Model mapping Exams to Centers.
    Why it is required: Object-level authorization needs to know which centers
    are permitted to access which exams. This server-side data is trusted.
    """
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    center_id = Column(Integer, nullable=False, index=True)
    
    exam = relationship("Exam", back_populates="assigned_centers")

class Exam(Base):
    __tablename__ = "exams"
    """
    Exam Model
    Represents an examination (e.g., 'Midterm 2026'). 
    It serves as the parent entity for question papers and release sessions.
    """
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    exam_start = Column(DateTime, nullable=True)    # Day 6 Addition
    release_start = Column(DateTime, nullable=True) # Day 3 Addition
    release_end = Column(DateTime, nullable=True)   # Day 3 Addition
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    papers = relationship("Paper", back_populates="exam")
    assigned_centers = relationship("ExamCenter", back_populates="exam")

class Paper(Base):
    __tablename__ = "papers"
    """
    Paper Model
    Represents a question paper. Has a foreign key to the `exams` table.
    Day 3: Added fields to track ownership, storage, and encryption metadata securely.
    """
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    
    # Day 3 Additions
    storage_object_id = Column(String, nullable=True) # Pointer to R2 bucket object
    status = Column(String, nullable=False, default="DRAFT") # Day 6 formalization
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_hash = Column(String, nullable=True)
    encryption_metadata = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    exam = relationship("Exam", back_populates="papers")
    approvals = relationship("Approval", back_populates="paper")
    creator = relationship("User")

class Approval(Base):
    __tablename__ = "approvals"
    """
    Approval Model
    Tracks the approvals of a paper by various reviewers and controllers.
    """
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default="pending") # e.g., pending, approved, rejected
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    paper = relationship("Paper", back_populates="approvals")
