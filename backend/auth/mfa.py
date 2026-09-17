"""
File Overview:
This file implements Time-Based One-Time Password (TOTP) logic for MFA.

Important Functions:
- `generate_totp_secret`: Generates a base32 secret for a new user.
- `verify_totp`: Validates the 6-digit code provided by the user against their secret.

Why it is required:
High-privilege roles (like EXAM_CONTROLLER) require a second factor of authentication
to prevent unauthorized access even if the password is compromised.
"""
import pyotp

# Define which roles require MFA
MFA_REQUIRED_ROLES = ["EXAM_CONTROLLER", "AUDITOR"]

def generate_totp_secret() -> str:
    """
    Generates a secure random base32 string to serve as the user's TOTP secret.
    """
    return pyotp.random_base32()

def verify_totp(secret: str, code: str) -> bool:
    """
    Verifies the provided 6-digit code against the TOTP secret.
    """
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
