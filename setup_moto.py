import os
import boto3
import json
import sqlite3
import sys

# Ensure we can import from backend
sys.path.append("/home/kameshwarank/.gemini/antigravity/scratch/stleds")

def setup():
    # Configure boto3 to use Moto server
    endpoint_url = "http://127.0.0.1:5000"
    
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["KMS_ENDPOINT"] = endpoint_url
    
    # 1. Create KMS Key and Alias
    kms = boto3.client('kms', region_name='us-east-1', endpoint_url=endpoint_url,
                       aws_access_key_id='test', aws_secret_access_key='test')
    
    try:
        response = kms.create_key(
            Description='STLEDS Master Key',
            KeyUsage='ENCRYPT_DECRYPT',
            Origin='AWS_KMS'
        )
        key_id = response['KeyMetadata']['KeyId']
        print(f"Created KMS Key: {key_id}")
        
        kms.create_alias(
            AliasName='alias/stleds-master-key',
            TargetKeyId=key_id
        )
        print("Created KMS Alias: alias/stleds-master-key")
    except Exception as e:
        print(f"KMS setup error: {e}")
        return

    # 2. Repair Paper 20 to use the new KMS key
    try:
        from backend.crypto.kms_client import kms_encrypt
        from backend.crypto.splitting import split_key
        from backend.crypto.engine import generate_key, generate_nonce, encrypt_document
        from backend.storage.r2 import upload_object
        
        with open("sample_paper.pdf", "rb") as f:
            plaintext = f.read()
            
        dek = generate_key()
        nonce = generate_nonce()
        ciphertext = encrypt_document(plaintext, dek, nonce)
        
        # Upload to mocked R2
        storage_object_id = upload_object(ciphertext)
        
        # Split and encrypt DEK
        share_a, share_b = split_key(dek)
        
        kms_share_a = kms_encrypt(share_a)
        kms_share_b = kms_encrypt(share_b)
            
        meta = {
            "kms_share_a": kms_share_a,
            "kms_share_b": kms_share_b,
            "document_nonce_b64": nonce.hex()
        }
        
        # Update SQLite database safely
        conn = sqlite3.connect("stleds.db")
        c = conn.cursor()
        c.execute("UPDATE papers SET storage_object_id = ?, encryption_metadata = ? WHERE id = 20", 
                  (storage_object_id, json.dumps(meta)))
        conn.commit()
        conn.close()
        print("Paper 20 has been successfully repaired and synchronized with the new KMS Master Key.")
    except Exception as e:
        print(f"Warning: Could not repair Paper 20: {e}")

if __name__ == "__main__":
    setup()
