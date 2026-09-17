"""
File Overview:
This module provides cryptographic primitives for encrypting and decrypting question papers.

Important Functions:
- `generate_key()`: Creates a 256-bit AES DEK.
- `generate_nonce()`: Creates a 96-bit nonce for AES-GCM.
- `encrypt_document()`: Encrypts plaintext using AES-256-GCM, returning ciphertext and auth tag.
- `decrypt_document()`: Decrypts ciphertext using AES-256-GCM. If tampering is detected, it raises an exception.
- `verify_integrity()`: Alias for `decrypt_document` to prove integrity logic is built-in.

Security Context:
- We use AES-GCM (Galois/Counter Mode) because it provides both Confidentiality and Integrity (Authenticated Encryption).
- Nonces MUST be unique for every encryption operation under the same key. A 96-bit random nonce is standard for GCM.
- If ciphertext or the authentication tag is modified, decryption safely fails without exposing partial plaintext.
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

def generate_key() -> bytes:
    """
    Generates a cryptographically secure 256-bit (32 byte) key for AES.
    Why it is required: AES-256 requires a 256-bit key. Using `os.urandom` ensures
    it is generated securely from the OS's cryptographically secure pseudo-random number generator (CSPRNG).
    """
    return AESGCM.generate_key(bit_length=256)

def generate_nonce() -> bytes:
    """
    Generates a cryptographically secure 96-bit (12 byte) nonce for AES-GCM.
    Why it is required: GCM requires a unique nonce for every encryption operation.
    Reusing a nonce compromises the security of the cipher. 96 bits is the recommended length.
    """
    return os.urandom(12)

def encrypt_document(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """
    Encrypts the plaintext using AES-256-GCM.
    
    Why it is required: Ensures the document is unreadable to anyone without the key.
    How it works: `AESGCM` computes the ciphertext and appends the 16-byte authentication tag
    to the end of the ciphertext bytes automatically.
    """
    aesgcm = AESGCM(key)
    # The encrypt method returns ciphertext + auth tag combined
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return ciphertext

def decrypt_document(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    """
    Decrypts the ciphertext using AES-256-GCM.
    
    Why it is required: Reverses encryption for authorized users.
    How it works: AESGCM automatically verifies the authentication tag appended to the ciphertext.
    If the ciphertext or tag was modified (or the wrong key/nonce is used), an `InvalidTag` exception is raised.
    This guarantees we NEVER return unauthenticated plaintext.
    """
    aesgcm = AESGCM(key)
    try:
        # The decrypt method automatically extracts and verifies the auth tag.
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        return plaintext
    except InvalidTag:
        # Tampering detected!
        raise ValueError("Integrity check failed: Ciphertext or Auth Tag is invalid/tampered.")

def verify_integrity(ciphertext: bytes, key: bytes, nonce: bytes) -> bool:
    """
    Verifies the integrity of the encrypted document by attempting to decrypt it.
    If successful, integrity is proven.
    """
    try:
        decrypt_document(ciphertext, key, nonce)
        return True
    except ValueError:
        return False
