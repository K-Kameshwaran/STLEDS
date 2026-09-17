"""
File Overview:
This module simulates a Key Management Service (KMS) for protecting Data Encryption Keys (DEKs).

Important Functions:
- `wrap_key()`: Encrypts a generated DEK using the application's Key Encryption Key (KEK).
- `unwrap_key()`: Decrypts the DEK back into plaintext for use during document decryption.

Why it is required:
Storing a raw DEK next to ciphertext in the database completely defeats the purpose of encryption.
We must wrap (encrypt) the DEK with a master key (KEK). In production, this KEK resides in AWS KMS or Google Cloud KMS.
For Day 4, we use a static environment variable to simulate this master key architecture.
"""
import os
import base64
from backend.crypto.engine import encrypt_document, decrypt_document

# In a real application, this should NEVER be hardcoded or checked into source control.
# It simulates the external KMS master key.
MASTER_KEK = os.getenv("APP_MASTER_KEK", b"12345678901234567890123456789012").ljust(32, b'0')[:32]

def wrap_key(dek: bytes) -> dict:
    """
    Encrypts the DEK using the Master KEK.
    Returns a dictionary containing the wrapped DEK and the nonce used to wrap it.
    """
    # We generate a unique nonce just for wrapping this specific DEK
    wrap_nonce = os.urandom(12)
    wrapped_dek = encrypt_document(dek, MASTER_KEK, wrap_nonce)
    
    return {
        "wrapped_dek_b64": base64.b64encode(wrapped_dek).decode('utf-8'),
        "wrap_nonce_b64": base64.b64encode(wrap_nonce).decode('utf-8')
    }

def unwrap_key(wrapped_dek_b64: str, wrap_nonce_b64: str) -> bytes:
    """
    Decrypts the wrapped DEK using the Master KEK.
    """
    wrapped_dek = base64.b64decode(wrapped_dek_b64)
    wrap_nonce = base64.b64decode(wrap_nonce_b64)
    
    return decrypt_document(wrapped_dek, MASTER_KEK, wrap_nonce)
