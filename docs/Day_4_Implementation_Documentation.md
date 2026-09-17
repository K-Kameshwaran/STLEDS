# Day 4 Implementation Documentation: Encryption and Secure Question-Paper Storage

## 1. Day 4 Overview
This document summarizes the work completed during Day 4. The primary objective was to ensure that Question Papers are encrypted *before* persistent storage, guaranteeing that no plaintext ever resides in the R2 object store. We implemented a robust AES-256-GCM encryption pipeline, secure Key Management simulation (KMS), and a simulated private R2 storage bucket to prove the architecture.

## 2. Encryption Architecture
The encryption architecture follows the Envelope Encryption pattern:
1. A unique Data Encryption Key (DEK) is generated for every paper.
2. The paper is encrypted using AES-256-GCM with the DEK.
3. The DEK itself is encrypted (wrapped) using a master Key Encryption Key (KEK) simulating a KMS.
4. The wrapped DEK is stored alongside the paper metadata in the database.

## 3. AES-256-GCM Implementation
The cryptographic module `backend/crypto/engine.py` relies on the robust `cryptography` library.
- **Algorithm**: AES-256 in Galois/Counter Mode (GCM).
- **Confidentiality**: Ensured via 256-bit keys and strong cipher logic.
- **Integrity**: GCM natively provides an authentication tag (appended to the ciphertext) which is strictly validated during decryption.

## 4. Key and Nonce Generation
- **Key Generation**: 256-bit (32 byte) keys are generated using `AESGCM.generate_key()`, which draws from `os.urandom`.
- **Nonce Generation**: 96-bit (12 byte) nonces are generated for every single encryption operation using `os.urandom(12)`. Nonce uniqueness is guaranteed through the vast CSPRNG space.

## 5. Key Protection Strategy (KMS Simulation)
Raw DEKs are never stored in the database. The `backend/crypto/kms.py` module uses a static environment variable `APP_MASTER_KEK` to wrap the DEKs via a secondary AES-GCM operation.
*Note: In production, `APP_MASTER_KEK` would be replaced by AWS KMS or Google Cloud KMS SDK calls. For the Day 4 sandbox, this simulated approach proves the architecture.*

## 6. Upload Pipeline
The `/exams/papers` endpoint was refactored:
1. **Input Validation**: Accepts `multipart/form-data` validating file presence, size (<10MB), and type (application/pdf).
2. **In-Memory Processing**: The file is read into memory as temporary plaintext.
3. **Encryption**: Generates a DEK/Nonce and performs AES-GCM. The plaintext variable is explicitly overwritten (`plaintext = b""`).
4. **Upload**: The ciphertext is streamed to `backend/storage/r2.py`.
5. **Metadata Storage**: The wrapped DEK, document nonce, and storage ID are saved to PostgreSQL (SQLite locally).

## 7. R2 Storage Architecture
Due to the lack of external cloud credentials in the Day 4 sandbox, a strict local directory (`backend/storage/local_r2_bucket`) simulates the Cloudflare R2 bucket. It exposes `upload_object` and `download_object` methods. This directory is strictly private; there are no public routing configurations exposing its contents.

## 8. Document Hashing and Metadata
- **Document Hash**: A SHA-256 hash of the original plaintext is generated and stored in the database for later watermark/integrity comparisons.
- **Encryption Metadata**: Stored as a JSON string in the `Paper` model, containing `wrapped_dek_b64`, `wrap_nonce_b64`, and `document_nonce_b64`.

## 9. Integrity Protection & Tamper Detection
AES-GCM guarantees that any modification to the ciphertext or the authentication tag will cause the `decrypt()` method to raise an `InvalidTag` exception. We explicitly catch this and raise a safe 500 error, never returning tampered plaintext.

## 10. Testing Strategy & Actual Verification Results
We engineered an exhaustive Pytest suite (`tests/test_encryption.py`):
1. **End-to-End Upload/Download**: Successfully encrypted via Setter, stored in R2, and decrypted via Center. (PASSED)
2. **Raw Storage Verification**: Directly inspected the raw file in the `local_r2_bucket`. Verified it did NOT start with `%PDF-` and was indistinguishable binary ciphertext. (PASSED)
3. **Modified Ciphertext**: Flipped a bit in the middle of the ciphertext. Decryption forcefully rejected it. (PASSED)
4. **Modified Authentication Tag**: Flipped a bit in the final 16 bytes (auth tag). Decryption forcefully rejected it. (PASSED)
5. **Wrong Key**: Attempted decryption with a newly generated DEK. Decryption forcefully rejected it. (PASSED)

## 11. Problems Encountered & Solutions Applied
- *Requirement for R2 Storage without Credentials*: We abstracted the storage logic into `backend/storage/r2.py` utilizing local file I/O to simulate the R2 bucket exactly, allowing us to perform the mandatory "Raw Storage Inspection" test successfully.
- *Pytest Assertions*: Initially, the wrong key test checked for `InvalidTag` but our wrapper properly raised a `ValueError`. The test was immediately corrected.

## 12. Security Considerations & Error Handling
- **Failing Safely**: Any decryption failure results in a generic `500 Integrity check failed` error, masking cryptographic internals.
- **No Plaintext Persistence**: The pipeline proves that plaintext exists only briefly in memory during the `encrypt()` cycle.

## 13. Future Work
- Swap the mock KMS (`backend/crypto/kms.py`) for a real Cloud KMS SDK.
- Swap the mock R2 (`backend/storage/r2.py`) for `boto3` utilizing AWS S3 compatibility APIs for Cloudflare R2.

## 14. Definition of Done
The Definition of Done has been entirely met. Question papers are verifiably encrypted using AES-256-GCM before persistent storage. Key architecture safely isolates DEKs. Tampering is immediately detected and rejected, and raw storage holds nothing but binary ciphertext.
