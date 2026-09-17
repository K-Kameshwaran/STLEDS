# Day 5 Implementation Documentation: Key Protection and Dual-Custodian Authorization

## 1. Day 5 Overview
This document summarizes the Day 5 implementation for the `stleds` project. The core objective was to architect and enforce a strict **Dual-Custodian Authorization** model. The goal is simple: no single actor, including system administrators or high-level executives, can unilaterally decrypt and release a question paper. Authorization requires the mathematical combination of cryptographic materials held by two distinct roles: the **Exam Controller** (Custodian A) and the **External Observer** (Custodian B).

## 2. Security Objective & Scope Clarification
> [!IMPORTANT]
> **Scope Limitation**: The two-party mechanism implemented here is designed strictly to enforce the *separation of authorization responsibilities*. It ensures that the application logic requires two authenticated identities to approve a release. It is **not** a defense against total root server compromise or an advanced persistent threat (APT) that successfully dumps the database and memory simultaneously while the release session is active.

## 3. Key Architecture & DEK Protection
During Day 4, papers were encrypted using a unique Data Encryption Key (DEK). In Day 5, we integrated a Key Splitting mechanism into the upload pipeline:
1. The DEK is mathematically split into `Share A` and `Share B` using cryptographic XOR (`DEK = Share A ^ Share B`). 
2. Because this is an XOR split, possessing only one share reveals absolutely nothing about the DEK (perfect secrecy).
3. The raw DEK is purged from memory.

## 4. AWS KMS Integration
To protect the shares at rest, we integrated **AWS KMS (Key Management Service)**.
- `Share A` and `Share B` are independently encrypted using `kms:Encrypt` before being stored in the PostgreSQL database.
- We implemented `backend/crypto/kms_client.py` utilizing `boto3`. AWS credentials are drawn exclusively from environment variables or attached IAM roles; they are never hardcoded.
- **KMS Key Policy**: In production, the KMS Key Policy MUST be configured with Least Privilege. Specifically, it should only allow `kms:Decrypt` actions to the `arn:aws:iam::ACCOUNT_ID:role/stleds-backend-execution-role`.

## 5. Dual-Custodian Workflow
The release pipeline is governed by `backend/release/router.py`:
1. **Create Session**: An admin initiates a `ReleaseSession` for a specific Exam.
2. **Authorize**: Custodian A (Exam Controller) and Custodian B (External Observer) submit authorization payloads to `POST /release/sessions/{id}/authorize`. 
3. **Execute**: The system evaluates the session via `POST /release/sessions/{id}/execute`. Only if both distinct unconsumed authorizations are present does the system transition the session to `active`.

## 6. Replay Protection
Replay protection is rigorously enforced to prevent an attacker or rogue admin from reusing an old authorization:
- **Binding**: Authorizations are strictly bound to the `user_id`, `exam_id`, and `release_session_id`.
- **Time Windows**: The authorization request requires a `client_timestamp`. The server rejects any timestamp older than 5 minutes or originating from the future.
- **Consumption**: Upon a successful `execute` operation, the utilized authorizations are marked `consumed = True` in the database. Subsequent execution attempts safely fail.

## 7. Decryption Execution
When a Center Superintendent requests to download a paper, the `download_paper` route:
1. Validates the `ReleaseSession` is `active`.
2. Fetches the KMS-encrypted shares from the database.
3. Invokes `kms:Decrypt` via AWS KMS.
4. XORs the plaintext shares to reconstruct the DEK.
5. Performs AES-256-GCM authenticated decryption.

## 8. Testing Strategy & Actual Verification Results
We engineered an extensive test suite (`tests/test_dual_custodian.py`) utilizing `moto` to simulate AWS KMS interactions dynamically:
- **Controller Only**: Attempted to execute release with only Custodian A. Result: **DENY** (403 Forbidden).
- **Observer Only**: Attempted to execute release with only Custodian B. Result: **DENY** (403 Forbidden).
- **Both Custodians**: Authorized with both roles. Result: **ALLOW** (200 OK).
- **Replay Attack (Consumed)**: Attempted to execute a second time using already consumed authorizations. Result: **DENY** (400 Bad Request).
- **Replay Attack (Stale Timestamp)**: Submitted an authorization with a 10-minute old timestamp. Result: **DENY** (400 Bad Request).
- **Role Validation**: Attempted to authorize using a `QUESTION_SETTER` token. Result: **DENY** (403 Forbidden).

## 9. Error Handling
The system employs a strict fail-closed methodology. If KMS fails, a share is corrupted, or authorization is insufficient, the system traps the error and returns a generic `403` or `500` error, ensuring cryptographic state and missing materials are never leaked to the client.

## 10. Problems Encountered & Solutions
- *AWS Credentials in Sandbox*: We utilized `moto` to intercept `boto3` calls globally during pytest execution. This allowed us to write genuine production AWS SDK code while verifying logic locally without exposing real cloud bills or credentials.
- *Testing Context Leaks*: We identified that `boto3.client` was resolving environment variables at module import time, causing tests to fail after the first run. The solution was refactoring `kms_client.py` to resolve the `KMS_KEY_ID` dynamically during the function invocation.

## 11. Final Summary
The Day 5 requirements have been completely fulfilled. By combining cryptographic Key Splitting (XOR), Envelope Encryption via AWS KMS, and rigorous API-level replay protection, we have guaranteed that the decryption of a question paper unequivocally requires the active, time-bound participation of both designated custodians.
