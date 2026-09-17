"""
File Overview:
This module implements a cryptographic Key Splitting mechanism using XOR.

Important Functions:
- `split_key()`: Splits a Master Key Encryption Key (KEK) into two shares.
- `reconstruct_key()`: Recombines the two shares to recover the Master KEK.

Security Context:
- A simple XOR split ensures that possessing only one share reveals absolutely nothing about the original key (Perfect Secrecy, mathematically equivalent to a One-Time Pad).
- The operation is: Share B = Master KEK ^ Share A.
- Rebuilding is: Master KEK = Share A ^ Share B.
- Neither the Controller (Custodian A) nor the Observer (Custodian B) can independently complete the release. Both shares MUST be submitted and successfully decrypted by KMS.
"""
import os

def split_key(master_kek: bytes) -> tuple[bytes, bytes]:
    """
    Splits the master key into Share A and Share B.
    
    Why it is required: Prevents a single ordinary actor from unilaterally recovering the KEK.
    """
    if len(master_kek) != 32:
        raise ValueError("Master KEK must be exactly 32 bytes (256 bits).")
        
    # Generate Share A randomly
    share_a = os.urandom(32)
    
    # Compute Share B using XOR
    share_b = bytes([a ^ b for a, b in zip(master_kek, share_a)])
    
    return share_a, share_b

def reconstruct_key(share_a: bytes, share_b: bytes) -> bytes:
    """
    Reconstructs the master key by XORing Share A and Share B.
    
    Why it is required: Dual-Custodian Authorization must combine both valid materials
    to actually perform the decryption operation.
    """
    if len(share_a) != 32 or len(share_b) != 32:
        raise ValueError("Key shares must be exactly 32 bytes.")
        
    master_kek = bytes([a ^ b for a, b in zip(share_a, share_b)])
    return master_kek
