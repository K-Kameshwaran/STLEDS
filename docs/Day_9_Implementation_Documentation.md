# Day 9: Complete Security Testing and Bug Fixing

## Objective

The objective of Day 9 is to attack the system like an evaluator, rigorously testing all security mechanisms introduced in the previous days rather than simply verifying the happy path. This milestone acts as the final security gate, ensuring that the examination question-paper management system fails closed in all integrity, authorization, and cryptographic failures.

## Test Strategy

A comprehensive automated test suite using `pytest` was developed and executed to ensure exhaustive coverage of:

1. **Authentication:** Verification of invalid passwords, unknown users, expired/invalid tokens, inactive accounts, and mandatory MFA validation for privileged roles.
2. **Authorization:** Role-Based Access Control (RBAC) validation across critical endpoints (e.g., ensuring Setters cannot trigger releases, Centers cannot access wrong papers, etc.).
3. **Encryption:** Verification of ciphertext tampering, authentication tag manipulation, correct key derivation, and missing key handling.
4. **Time-Based Release & Dual-Custodian:** Verification of the complete state machine, enforcing time windows, replay protection, and the strict requirement for both Controller and Observer authorization.
5. **Audit Logging:** Verification of mathematical hash-chain integrity, detecting tampering of historical audit records.
6. **End-to-End Lifecycle:** A comprehensive E2E test simulating the entire workflow from upload, encryption, authorization, release, and watermarked download.

## Bugs Discovered and Fixed

During the testing phase, several critical defects were identified and resolved:

### 1. Security Bugs
- **Missing RBAC on Release Sessions:** The `/release/sessions` endpoint lacked a role check, allowing any authenticated user to create a release session. **Fix:** Implemented an RBAC check in `create_release_session` to explicitly restrict access to `EXAM_CONTROLLER` and `EXTERNAL_OBSERVER`.
- **MFA Enforcement Gap:** While MFA logic was implemented, the End-to-End tests revealed that MFA codes were not properly passed by privileged roles during authentication, simulating a bypass. **Fix:** Ensured the authentication endpoint properly rejected privileged logins lacking the correct MFA code, and updated all tests to provide the required simulated TOTP code.

### 2. Functional and State Machine Bugs
- **State Machine Deadlock on Download:** The `download_paper` endpoint automatically transitioned the paper state to `RELEASED` upon successful download. However, the endpoint logic only permitted downloads when the effective state was exactly `RELEASE_WINDOW`. This created a deadlock where subsequent authorized downloads by Centers were erroneously denied. **Fix:** Updated the state machine check in `download_paper` to permit downloads in both `RELEASE_WINDOW` and `RELEASED` states.
- **Strict E2E Transitions:** The End-to-End test attempted to transition a paper directly from `ENCRYPTED` to `APPROVED`, skipping the required `PENDING_REVIEW` state. The state machine correctly rejected this. **Fix:** Updated the E2E lifecycle test to rigorously follow the correct transition sequence (`ENCRYPTED` -> `PENDING_REVIEW` -> `APPROVED` -> `LOCKED` -> `RELEASE_WINDOW`).

### 3. Testing Infrastructure and Isolation Issues
- **AWS Mocking Scope Leaks:** Encryption tests relying on `boto3.client('kms')` failed with `NoCredentialsError` because the AWS mocking (`moto`) was not properly scoped within the test modules, attempting to hit real AWS endpoints. **Fix:** Integrated `mock_aws` decorators and explicitly set AWS mock environment variables at the top-level test fixtures.
- **Test Database Leakage:** Tests executing in parallel or sequence encountered `sqlite3.OperationalError` due to shared SQLite states. **Fix:** Enforced strict database isolation using modular `test_*.db` SQLite files per test file, ensuring a clean schema and data state for each test run.
- **PDF Magic Byte Generation:** Authorization and encryption tests were failing at the download stage because the system's forensic watermarking library (`pypdf`) threw exceptions when attempting to watermark raw dummy bytes (`b"%PDF-1.4\n..."`). **Fix:** Integrated `reportlab` into the test suite to dynamically generate structurally valid PDF documents for upload and watermarking.

## Final Validation

The test suite now achieves a **100% pass rate across 46 security tests**. The system accurately rejects unauthorized access, detects ciphertext/audit tampering, enforces dual-custodian time-based release, and ensures secure, individualized delivery of examination papers.

Definition of Done criteria met: All critical security tests pass and no known blocking defect remains.
