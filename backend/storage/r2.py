"""
File Overview:
This file simulates Cloudflare R2 object storage operations.

Important Functions:
- `upload_object()`: Writes binary data to the simulated R2 storage directory.
- `download_object()`: Reads binary data from the simulated R2 storage directory.

Why it is required:
In this sandbox environment, we do not have external cloud credentials. However, the architecture
demands a strict separation between database metadata and raw file storage. By isolating file I/O
into this module, we can later seamlessly swap `local_r2_bucket` interactions for actual `boto3` calls.
The storage bucket is strictly PRIVATE. There are no public URLs exposed here.
"""
import os
import uuid

# Define the local directory acting as the private R2 bucket
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "local_r2_bucket")

# Ensure the storage directory exists
os.makedirs(STORAGE_DIR, exist_ok=True)

def _get_file_path(object_id: str) -> str:
    """Helper to resolve the object ID to a local file path."""
    # Prevent path traversal vulnerabilities by getting basename
    safe_id = os.path.basename(object_id)
    return os.path.join(STORAGE_DIR, safe_id)

def upload_object(data: bytes, object_id: str = None) -> str:
    """
    Simulates uploading an object to a private R2 bucket.
    Why encryption is performed before storage: The `data` parameter here will ALWAYS be ciphertext.
    Even if the R2 bucket is compromised, the attacker only gets unreadable binary data.
    """
    if not object_id:
        object_id = str(uuid.uuid4())
        
    file_path = _get_file_path(object_id)
    
    with open(file_path, "wb") as f:
        f.write(data)
        
    return object_id

def download_object(object_id: str) -> bytes:
    """
    Simulates downloading an object from a private R2 bucket.
    """
    file_path = _get_file_path(object_id)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Object {object_id} not found in storage.")
        
    with open(file_path, "rb") as f:
        return f.read()
