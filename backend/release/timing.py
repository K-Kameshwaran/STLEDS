"""
File Overview:
Provides a secure, consistent server-side time evaluation for the release window.

Important Functions:
- `get_current_utc_time`: The SINGLE source of truth for time within the release subsystem.
- `evaluate_time_state`: Determines if the current server time is BEFORE, INSIDE, or AFTER the release window.

Why it is required:
A client-side clock (browser/OS time) or a frontend-supplied timestamp can easily be manipulated by an attacker. 
The release decision must NEVER depend on the client's clock. This module enforces UTC-based server-side
time checks exclusively.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

class TimeState(Enum):
    BEFORE_WINDOW = "BEFORE_WINDOW"
    INSIDE_WINDOW = "INSIDE_WINDOW"
    AFTER_WINDOW = "AFTER_WINDOW"
    MISSING_WINDOW = "MISSING_WINDOW"

def get_current_utc_time() -> datetime:
    """
    Returns the current server time in UTC.
    This must be used for ALL release-timing decisions.
    """
    return datetime.now(timezone.utc)

def evaluate_time_state(release_start: Optional[datetime], release_end: Optional[datetime]) -> TimeState:
    """
    Determines the current state of the release window relative to the trusted server time.
    """
    if not release_start or not release_end:
        return TimeState.MISSING_WINDOW
        
    now = get_current_utc_time()
    
    # Ensure timezone awareness for safe comparisons
    if release_start.tzinfo is None:
        release_start = release_start.replace(tzinfo=timezone.utc)
    if release_end.tzinfo is None:
        release_end = release_end.replace(tzinfo=timezone.utc)
        
    if now < release_start:
        return TimeState.BEFORE_WINDOW
    elif now > release_end:
        return TimeState.AFTER_WINDOW
    else:
        return TimeState.INSIDE_WINDOW
