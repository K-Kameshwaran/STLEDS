# Day 8 Implementation Documentation: Audit Logging and Security Hardening

## 1. Day 8 Overview
This document summarizes the Day 8 implementation for the `stleds` project. The core objective was to implement a cryptographically secure, tamper-evident audit logging architecture and to harden the system against common web vulnerabilities (excessive payloads, brute-force logins, unsafe CORS).

## 2. Audit Logging Architecture
The Audit Logging system operates as a reusable module in `backend/audit/service.py`. It provides functions to log system events securely. 

### 2.1 Hash Chain Design
To detect manual database tampering, we implemented a hash chain:
- **Canonical Serialization**: Fields are converted into a strict, deterministic string format: `timestamp|actor_id|action|exam_id|resource_id|result|metadata_json`.
- **Genesis Hash**: The first record in the database references a hardcoded `GENESIS_HASH` (the SHA-256 hash of the string "GENESIS").
- **Current Hash**: Each record calculates its hash using: `SHA256(previous_hash + canonical_record_data)`.
- **Storage**: The database stores both `previous_hash` and `current_hash`.

### 2.2 Tamper Verification (`/audit/verify`)
The verification endpoint restricted to authorized users reconstructs the chain:
1. Iterates through all records in chronological order.
2. Asserts the `previous_hash` of row N matches the `current_hash` of row N-1.
3. Re-serializes the canonical data for row N.
4. Recalculates the expected `current_hash` and compares it against the stored value.
5. Fails and returns the ID of the `first_invalid_record` if any discrepancy is found.

### 2.3 Integrated Events
Audit logging has been successfully injected into the application's actual workflows without creating duplicated logic:
- `LOGIN_SUCCESS` / `LOGIN_FAILURE`: Authenticated and unauthenticated brute-force attempts.
- `UPLOAD`: Successfully uploaded papers and validation rejections.
- `REVIEW` / `APPROVAL`: Specific state transitions.
- `RELEASE_AUTHORIZED` / `RELEASE_ATTEMPT`: Dual-Custodian authorizations.
- `DOWNLOAD` / `UNAUTHORIZED_ACCESS` / `INTEGRITY_FAILURE`: Paper retrieval attempts.

## 3. Security Hardening
In addition to auditing, several critical security features were deployed.

### 3.1 Input & File Validation
- **Magic Bytes Validation**: `create_paper` now inspects the first 4 bytes of the uploaded file to ensure it starts with `%PDF`. Extension-based validation is insufficient as attackers can easily rename malicious binaries.
- **File-Size Limits**: Uploads are strictly capped at 20MB.

### 3.2 Rate Limiting
- Integrated `slowapi` (an in-memory limiter based on remote addresses).
- **Brute-Force Protection**: The `/auth/login` endpoint is now restricted to `5/minute` per IP.

### 3.3 Safe CORS Configuration
- Removed the unsafe `allow_origins=["*"]` wildcard.
- **Least Privilege**: The backend now defaults to `http://localhost:3000` but allows overriding via the `CORS_ALLOWED_ORIGINS` environment variable.

### 3.4 Secret Management & Cloud Credentials
- Removed hardcoded fallback secrets for `JWT_SECRET` in production environments.
- Enforced a runtime crash (`RuntimeError`) if the `JWT_SECRET` is missing and `ENV=production`.
- AWS/Cloudflare configurations rely strictly on environment variables and IAM role injection, avoiding plaintext credential exposure in the source code.

## 4. Testing and Verification Results
A dedicated test suite was implemented and successfully executed using `pytest`.

### 4.1 Audit Chain Tamper Detection (`test_audit_chain.py`)
- **Actually verified**: Created a legitimate audit chain of 3 records. Re-verified successfully.
- **Actually verified**: Intentionally modified the `action` field of record ID 2 directly via SQLAlchemy.
- **Actually verified**: The `/audit/verify` logic correctly rejected the chain and precisely identified record ID 2 as the source of the tamper.

### 4.2 Security Hardening (`test_security_hardening.py`)
- **Actually verified**: Fired 6 rapid requests to `/auth/login`. The 6th request was correctly blocked with `429 Too Many Requests`.
- **Actually verified**: Attempted to upload a 21MB mock payload; safely rejected by the 20MB cap.
- **Actually verified**: Attempted to upload a file named `fake.pdf` but containing non-PDF binary data (a Windows executable `MZ` header). The upload was safely rejected.

## 5. Final Summary
The Day 8 Definition of Done has been entirely satisfied. Important system actions are successfully recorded, the audit logs are cryptographically verifiable, and intentional database modifications are immediately mathematically detectable. The application is now significantly hardened against brute-force abuse and malicious payloads.
