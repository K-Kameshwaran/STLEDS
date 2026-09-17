"""
File Overview:
This file encapsulates AWS KMS (Key Management Service) interactions for the application.

Important Functions:
- `get_kms_client()`: Initializes the boto3 KMS client.
- `kms_encrypt()`: Encrypts plaintext (e.g. a Key Share) using the configured AWS KMS Key.
- `kms_decrypt()`: Decrypts ciphertext back into plaintext.

Security Context:
- AWS credentials are NOT hardcoded. boto3 securely infers them from the environment (e.g. IAM Roles, env vars).
- In production, the KMS Key Policy MUST enforce Least Privilege, explicitly granting `kms:Decrypt` ONLY to the specific IAM Role assumed by the backend application.
- The `APP_KMS_KEY_ID` must point to a symmetric KMS key.
"""
import os
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
import base64

# The ARN or ID of the AWS KMS key.
# In a local sandbox, if this is not set, we default to a dummy string that Moto can mock.
KMS_KEY_ID = os.getenv("APP_KMS_KEY_ID", "alias/stleds-master-key")

# We configure the region, usually inferred from AWS_DEFAULT_REGION
REGION_NAME = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

def get_kms_client():
    """
    Returns an initialized boto3 KMS client.
    """
    endpoint_url = os.getenv("KMS_ENDPOINT", os.getenv("R2_ENDPOINT", "http://127.0.0.1:5000"))
    return boto3.client(
        'kms',
        region_name=REGION_NAME,
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "testing"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "testing")
    )

def kms_encrypt(plaintext: bytes) -> str:
    """
    Encrypts the plaintext using AWS KMS.
    Returns the Base64 encoded ciphertext.
    
    Why it is required: Protects the key shares so they are useless if the database is compromised.
    """
    client = get_kms_client()
    key_id = os.getenv("APP_KMS_KEY_ID", "alias/stleds-master-key")
    try:
        response = client.encrypt(
            KeyId=key_id,
            Plaintext=plaintext
        )
        ciphertext_blob = response['CiphertextBlob']
        return base64.b64encode(ciphertext_blob).decode('utf-8')
    except ClientError as e:
        print("KMS ENCRYPT ERROR:", e)
        # We must NOT leak the underlying AWS error details to the frontend.
        raise HTTPException(status_code=500, detail="Key protection operation failed.")

def kms_decrypt(ciphertext_b64: str) -> bytes:
    """
    Decrypts the Base64 encoded ciphertext using AWS KMS.
    
    Why it is required: Recovers the key share during the Dual-Custodian release workflow.
    """
    client = get_kms_client()
    try:
        ciphertext_blob = base64.b64decode(ciphertext_b64)
        response = client.decrypt(
            CiphertextBlob=ciphertext_blob
        )
        return response['Plaintext']
    except ClientError as e:
        # Failing closed on KMS decryption failure
        raise HTTPException(status_code=500, detail="Key recovery operation failed.")
