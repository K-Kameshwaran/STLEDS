"""
File Overview:
This file handles object storage operations (AWS S3 / Cloudflare R2).

Important Functions:
- `upload_object()`: Writes binary data to the storage backend.
- `download_object()`: Reads binary data from the storage backend.

Why it is required:
In production, we must write securely encrypted PDF files to persistent external storage
so that serverless/ephemeral instances do not lose data.
"""
import os
import uuid
import boto3
from botocore.exceptions import ClientError

# Define the local directory acting as the fallback private R2 bucket
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "local_r2_bucket")
os.makedirs(STORAGE_DIR, exist_ok=True)

def _get_s3_client():
    """Initializes the S3/R2 client for production."""
    endpoint_url = os.getenv("R2_ENDPOINT")
    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name=os.getenv("R2_REGION", "auto")
    )

def upload_object(data: bytes, object_id: str = None) -> str:
    """
    Uploads an object to the storage backend.
    """
    if not object_id:
        object_id = str(uuid.uuid4())
        
    bucket_name = os.getenv("R2_BUCKET_NAME")
    env = os.getenv("ENVIRONMENT", "production")
    
    if bucket_name and env != "development":
        # Production: Cloud Storage
        try:
            s3 = _get_s3_client()
            s3.put_object(Bucket=bucket_name, Key=object_id, Body=data)
        except ClientError as e:
            print("S3 UPLOAD ERROR:", e)
            raise RuntimeError("Cloud storage upload failed.")
    else:
        # Local Development Fallback
        safe_id = os.path.basename(object_id)
        file_path = os.path.join(STORAGE_DIR, safe_id)
        with open(file_path, "wb") as f:
            f.write(data)
            
    return object_id

def download_object(object_id: str) -> bytes:
    """
    Downloads an object from the storage backend.
    """
    bucket_name = os.getenv("R2_BUCKET_NAME")
    env = os.getenv("ENVIRONMENT", "production")
    
    if bucket_name and env != "development":
        # Production: Cloud Storage
        try:
            s3 = _get_s3_client()
            response = s3.get_object(Bucket=bucket_name, Key=object_id)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"Object {object_id} not found in cloud storage.")
            print("S3 DOWNLOAD ERROR:", e)
            raise RuntimeError("Cloud storage download failed.")
    else:
        # Local Development Fallback
        safe_id = os.path.basename(object_id)
        file_path = os.path.join(STORAGE_DIR, safe_id)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Object {object_id} not found in local storage.")
        with open(file_path, "rb") as f:
            return f.read()
