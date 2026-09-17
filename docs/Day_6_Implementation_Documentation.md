# Day 6 Implementation Documentation: Controlled and Time-Based Release

## 1. Day 6 Overview
This document summarizes the Day 6 implementation for the `stleds` project. The core objective was to implement a **scheduled and controlled question-paper release mechanism**. We centralized the release rules into an atomic server-side evaluation that prevents any premature release and fully enforces all prior security requirements (RBAC, Dual-Custodian Auth, KMS Key Auth, Integrity Checks).

## 2. Security Claim Constraint
> [!IMPORTANT]
> **Why This Is Not Cryptographic Time-Locking**:
> The existence of `release_start` and `release_end` in the database does **not** constitute cryptographic time-locking (which involves verifiable delay functions or time-lock puzzles where ciphertext is mathematically unsolvable until time has passed). 
> 
> The control implemented here is explicitly defined as:
> **Server-side scheduled release + infrastructure-level key authorization controls**.
> Time validation occurs at the application layer, which then gates access to the infrastructure layer (KMS).

## 3. Release Lifecycle & States
We defined an explicit state machine for a `Paper` with the following states:
```text
DRAFT -> ENCRYPTED -> PENDING_REVIEW -> APPROVED -> LOCKED -> RELEASE_WINDOW -> RELEASED -> EXPIRED -> ARCHIVED
```
- **Valid State Transitions**: Transitions are enforced server-side via `backend/release/state_machine.py`. A client cannot directly override a state (e.g., forcing a paper into `RELEASED` via a payload modification).
- **Dynamic Time Resolution**: Some states like `RELEASE_WINDOW` and `EXPIRED` are dynamically resolved by comparing the current UTC server time against the `Exam` time window. This prevents reliance on cron jobs and strictly evaluates the time at the exact moment of the download request.

## 4. Release Window Design & Server-Side Time Validation
- The `Exam` model was updated to track `exam_start`, `release_start`, and `release_end`.
- The `backend/release/timing.py` module strictly uses `datetime.now(timezone.utc)` for all time evaluations.
- **Never Trusted**: The client's system clock, frontend timestamps, and arbitrary `is_released` boolean payloads are wholly ignored during the release decision.

## 5. Release Conditions (Fail-Closed Execution)
The `download_paper` endpoint in `backend/exams/router.py` was refactored to perform an **Atomic Release Decision**. If any single condition is false, the request fails closed immediately.

The exact conditions required for release are:
1. **Paper Approval**: The paper must be approved and scheduled (resulting in an effective `RELEASE_WINDOW` state).
2. **Server Time Inside Allowed Release Window**: Evaluated natively during effective state resolution.
3. **Controller Authorized**: `ReleaseSession` must be active.
4. **External Observer Authorized**: `ReleaseSession` must be active.
5. **Key Authorization**: `kms_decrypt` must return valid key material.
6. **Paper Integrity Verified**: `decrypt_document` (AES-256-GCM) must validate the authentication tag successfully.

## 6. AWS KMS Policy Validation
- **Integration**: `backend/crypto/kms_client.py` continues to route `kms_encrypt` and `kms_decrypt` requests dynamically.
- **Validation**: Because this prototype runs in a local sandbox, we cannot apply a live AWS IAM Policy. However, using the `moto` AWS SDK mocking framework, we were able to strictly mock the KMS execution paths and verify that the application properly routes decryption requests.
- **Expected Production Behavior**: In a real AWS environment, the `kms:Decrypt` action must be strictly scoped in the Key Policy to the backend Execution Role (`arn:aws:iam::ACCOUNT_ID:role/stleds-backend`).

## 7. Testing Strategy
We implemented rigorous testing in `tests/test_time_based_release.py`. Instead of using unreliable time-mocking libraries, we dynamically altered the `Exam`'s `release_start` and `release_end` timestamps in the test database to simulate time states.

### Actual Verification Results
1. **Before-Window Test**: Tested a fully authorized paper where `release_start` was set 1 hour into the future.
   - *Result*: **DENY** (403 Forbidden). Evaluated state was `LOCKED`.
2. **Inside-Window Test**: Tested a fully authorized paper where current time was explicitly inside the window.
   - *Result*: **ALLOW** (200 OK). Evaluated state was `RELEASE_WINDOW` and all crypto checks passed.
3. **After-Window Test**: Tested a fully authorized paper where `release_end` was set 1 hour in the past.
   - *Result*: **DENY** (403 Forbidden). Evaluated state was `EXPIRED`.
4. **Additional Tests**:
   - *Unapproved Paper*: Tested a paper inside the window but with status `PENDING_REVIEW` instead of `APPROVED`/`LOCKED`. **DENY** (403).
   - *Invalid State Transition*: Attempted to transition from `ENCRYPTED` directly to `LOCKED` skipping approval. **DENY** (400).

## 8. Problems Encountered & Solutions Applied
- **Problem**: Time-dependent states (`RELEASE_WINDOW`) require continuous updating if stored statically in a database, risking race conditions or requiring heavy asynchronous workers.
- **Solution**: We implemented `get_effective_state()`. If a paper is marked `LOCKED` in the database, the server dynamically evaluates UTC time upon request. If time is inside the window, it returns `RELEASE_WINDOW`. This completely mitigates asynchronous sync issues.
- **Problem**: Test failures related to missing Center Superintendent assignments.
- **Solution**: Updated the test fixture to correctly map the CS user to an `ExamCenter`, honoring Day 3's Object-Level Authorization requirements.

## 9. Final Summary
The implementation successfully enforces a strict, fail-closed, atomic release mechanism driven purely by UTC server time and dual-custodian cryptography. The API explicitly denies premature releases. We have rigorously documented that this is an application/infrastructure control layer and not cryptographic time-locking. The Definition of Done has been entirely fulfilled.
