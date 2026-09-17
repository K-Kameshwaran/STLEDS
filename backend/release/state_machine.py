"""
File Overview:
Implements the Release State Machine to govern the lifecycle of a Question Paper.

Important Functions:
- `get_effective_state`: Dynamically calculates the true state of a paper by combining its stored database status with the trusted server-side time.
- `can_transition`: Validates if a state transition is legal, enforcing server-side business logic.

Why it is required:
A client must not be able to directly submit an arbitrary state (e.g., {"status": "RELEASED"}).
All transitions must be strictly controlled by the server. Furthermore, time-based states (like 
RELEASE_WINDOW and EXPIRED) must not rely on a cron job, but must be dynamically enforced at 
the exact moment of access.
"""
from typing import Optional
from backend.exams.models import Exam, Paper
from backend.release.timing import evaluate_time_state, TimeState

class PaperState:
    DRAFT = "DRAFT"
    ENCRYPTED = "ENCRYPTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    LOCKED = "LOCKED"             # Scheduled, waiting for time
    RELEASE_WINDOW = "RELEASE_WINDOW" # Inside time window
    RELEASED = "RELEASED"         # Successfully downloaded by center
    EXPIRED = "EXPIRED"           # After time window, not released? Or just closed.
    ARCHIVED = "ARCHIVED"

# Valid manual/API transitions
VALID_TRANSITIONS = {
    PaperState.DRAFT: [PaperState.ENCRYPTED],
    PaperState.ENCRYPTED: [PaperState.PENDING_REVIEW],
    PaperState.PENDING_REVIEW: [PaperState.APPROVED, PaperState.DRAFT], # Can be rejected back to draft
    PaperState.APPROVED: [PaperState.LOCKED],
}

def get_effective_state(paper: Paper, exam: Optional[Exam] = None) -> str:
    """
    Returns the effective lifecycle state of the paper.
    If the paper is LOCKED, we check the UTC server time against the Exam's release window.
    """
    current_db_status = paper.status.upper()
    
    if current_db_status == PaperState.LOCKED:
        if not exam:
            return current_db_status # Cannot resolve time without exam
            
        time_state = evaluate_time_state(exam.release_start, exam.release_end)
        
        if time_state == TimeState.BEFORE_WINDOW:
            return PaperState.LOCKED
        elif time_state == TimeState.INSIDE_WINDOW:
            return PaperState.RELEASE_WINDOW
        elif time_state == TimeState.AFTER_WINDOW:
            return PaperState.EXPIRED
            
    return current_db_status

def can_transition(current_state: str, new_state: str) -> bool:
    """
    Validates if a requested state transition is allowed by the server-side lifecycle rules.
    """
    current_state = current_state.upper()
    new_state = new_state.upper()
    allowed_next_states = VALID_TRANSITIONS.get(current_state, [])
    return new_state in allowed_next_states
