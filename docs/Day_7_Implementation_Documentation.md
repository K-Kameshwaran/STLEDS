# Day 7 Implementation Documentation: Secure Delivery and Forensic Watermarking

## 1. Day 7 Overview
This document summarizes the Day 7 implementation for the `stleds` project. The core objective was to implement secure, individualized delivery of question papers by overlaying a visible forensic watermark onto the decrypted PDF. This ensures that any downloaded paper is uniquely identifiable to the exact center, user, and time it was accessed, preventing mass anonymous leaks.

## 2. Secure Delivery Architecture
The system employs a strict sequence of checks, terminating execution immediately if any check fails:
1. **Authentication Check**: Verifies the JWT and retrieves the `current_user`.
2. **Role Check**: Verifies the user has the `DOWNLOAD_ASSIGNED_PAPER` permission.
3. **Center/Exam Check**: Verifies the user's `center_id` is assigned to the requested `exam_id`.
4. **Release Validation**: Verifies the paper is explicitly in the `RELEASE_WINDOW` state.
5. **Authorization Validation**: Verifies Dual Custodian (`ReleaseSession`) is fully active.
6. **Key & Integrity Check**: Decrypts the KMS-wrapped DEK shares and decrypts the AES-256-GCM ciphertext, verifying integrity.
7. **Watermarking**: Dynamically overlays forensic text onto the plaintext PDF in memory.
8. **Delivery**: Returns the individualized PDF securely over HTTPS.

## 3. Trusted Identity and Timestamp
A critical security constraint was to never trust client-supplied identity or timing for the watermark.
- **Center ID & User ID**: Extracted from the validated JWT token and database `User` record (`current_user.center_id`, `current_user.id`).
- **Exam ID**: Extracted from the validated database `Paper` object (`paper.exam_id`).
- **Timestamp**: Extracted directly from the server using `datetime.now(timezone.utc)`.

## 4. Secure Decryption Flow & Plaintext Handling
- Ciphertext is downloaded securely from the private R2 instance.
- Decryption happens purely in memory.
- The `apply_watermark` function (using `pypdf` and `reportlab`) accepts raw `bytes`, applies the overlay, and returns raw `bytes`.
- The original plaintext is wiped from the Python variable immediately after the watermark is generated, minimizing its lifetime.
- The original unwatermarked paper is **never** saved to disk or returned to the client.

## 5. Visible Watermark Design
The forensic watermark is generated dynamically using `reportlab`. A transparent red overlay is constructed with the following information (tilted at 45 degrees, stamped on every page):
```text
EXAMINATION PAPER
EXAM ID: <exam_id>
CENTER ID: <center_id>
AUTHORIZED USER ID: <user_id>
TIMESTAMP: <UTC_TIMESTAMP>
```
The watermark is merged using `pypdf`, preserving the underlying visual content while stamping the identity across the page.

## 6. Scope / Why Advanced DRM Was Deferred
As per the Day 7 project specification, we focused entirely on a robust, visible watermarking system. Advanced digital rights management (DRM), steganography (invisible watermarking), or complex PDF fingerprinting were intentionally deferred. The priority was guaranteeing secure authorization and correct delivery of a traceable document.

## 7. Testing Strategy
We extended the existing `tests/test_time_based_release.py` to evaluate the secure delivery mechanism:
- **Mock PDF Generation**: Replaced the previous fake byte string with a valid, minimalistic PDF generated via `reportlab` to allow `pypdf` to parse and merge the watermark.
- **Watermark Verification**: We test that the returned response contains the watermarked bytes (e.g. asserting that the length of the document grows significantly, and that forensic text like `EXAMINATION PAPER` exists in the byte stream).
- **Wrong Center Test**: Introduced a test where `CS2` (assigned to Center 2) attempts to download a paper assigned to Center 1. The object-level authorization successfully fails closed (403 Forbidden).

## 8. Actual Verification Results
- **Center 101 → Own paper**: SUCCESS (200). Watermarked PDF delivered.
- **Center 101 → Center 102 paper**: DENIED (403). `Object access denied: Paper not assigned to your center`.
- **Unauthorized user**: DENIED (403). `Not enough permissions`.
- **Pre-release download**: DENIED (403). `Release Denied: Paper is not in RELEASE_WINDOW state`.
- **Released paper**: SUCCESS (200). 

## 9. HTTPS Delivery & R2 Protection
The framework's `Response(content=watermarked_pdf, media_type="application/pdf")` mechanism implicitly uses the application's HTTPS deployment wrapper in production. Direct URL access to R2 is impossible; the storage object ID is never exposed, and the credentials remain strictly on the backend.

## 10. Final Summary
The Day 7 Definition of Done is fully achieved. The application guarantees that an authorized examination center receives only its authorized, explicitly individualized paper. All security checks enforce a fail-closed paradigm, and plaintext is protected within memory for the shortest practical time.
