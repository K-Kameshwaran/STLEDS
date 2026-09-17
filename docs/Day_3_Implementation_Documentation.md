# Day 3 Implementation Documentation: RBAC, Object Authorization and Exam Workflow

## 1. Day 3 Overview
This document summarizes the work completed during Day 3. We extended the database schema to include critical examination and paper metadata, built out a strict Role-Based Access Control (RBAC) mechanism, and engineered rigorous server-side Object-Level Authorization. The system guarantees that even authenticated users can only interact with resources they explicitly own or have been assigned to.

## 2. RBAC Architecture
The RBAC system decouples specific roles from the core API routes by relying on granular permissions. Instead of a route verifying `role == "QUESTION_SETTER"`, it verifies `has_permission(upload_paper)`.

## 3. Role and Permission Mapping
A strict mapping is maintained within `backend/auth/rbac.py`:
- `QUESTION_SETTER`: `upload_paper`
- `REVIEWER`: `review_paper`
- `EXAM_CONTROLLER` / `EXTERNAL_OBSERVER`: `authorize_release`
- `CENTER_SUPERINTENDENT`: `download_assigned_paper`
- `AUDITOR`: `view_audit_data`

## 4. Authentication vs Authorization
- **Authentication**: Proving the user is who they say they are (handled in Day 2 via JWT).
- **Authorization**: Validating what the authenticated user is allowed to do. Day 3 forces APIs to evaluate identity against requested action *and* target object scope.

## 5. Route Authorization
Implemented using FastAPI dependencies within `backend/auth/dependencies.py`.
1. `get_current_user`: Ensures valid authentication.
2. `require_permission`: Asserts the authenticated user's role possesses the correct capability.

## 6. Object-Level Authorization
Authentication + Role Permission is not enough. If a user is a `CENTER_SUPERINTENDENT` and possesses `download_assigned_paper`, they must only be able to download papers explicitly assigned to their specific center.
This is strictly verified inside `get_paper_with_object_auth`.

## 7. Trusted Server-Side Authorization Context
Authorization derives purely from database states (`users.center_id`, `papers.created_by`, `exam_centers` mapping). If a client payload tries to manipulate the `center_id` or `user_id`, the server completely ignores the malicious payload, instead referencing the verified `sub` embedded in the JWT.

## 8. Examination Data Model
The `Exam` model (`backend/exams/models.py`) now safely stores scheduling and release metrics:
- `release_start`
- `release_end`

## 9. Paper Data Model
The `Paper` model securely captures state and encryption metadata without storing physical file bytes directly in the database:
- `storage_object_id`
- `status`
- `created_by`
- `document_hash`
- `encryption_metadata`

## 10. Database Relationships
An essential mapping model was introduced: `ExamCenter`. This serves as the association layer between `Exam` and authorized Centers, serving as the source of truth for downstream Center Superintendent object-level validations.

## 11. Authorization Workflow
When a `GET /exams/papers/{id}/download` request arrives:
1. Validate JWT. (Authentication)
2. Verify role has `download_assigned_paper`. (RBAC)
3. Lookup Paper, retrieve associated Exam.
4. Verify user's database `center_id` is mapped to the Exam via `ExamCenter`. (Object-Level).
5. If yes, return storage locator. If no, `403 FORBIDDEN`.

## 12. Security Considerations
- Deny by Default: Object authorization enforces fail-closed logic. If an exam has no mapped centers, all center-scoped access inherently fails.
- Client Manipulation: Payload ID manipulation is rendered entirely inert since object lookups trace through the JWT identity token to database foreign keys.

## 13. Error Handling
Failures safely return standard HTTP errors (`401` or `403`) without leaking underlying resource details. Accessing a center-mismatched paper returns a generic access denial rather than confirming internal relationship topologies.

## 14. Authorization Testing Strategy
We engineered `tests/test_authorization.py` utilizing pytest to assert both positive workflows and malicious vectors. We explicitly created intersecting entities (Center 101 vs Center 102) to guarantee cross-tenant boundaries.

## 15. Actual Verification Results
- **Missing Token**: `401 Unauthorized` (DENY)
- **Expired Token**: `401 Unauthorized` (DENY)
- **Wrong Role**: `403 Forbidden` (DENY) - Question Setter attempting download.
- **Wrong Center (Cross-Tenant)**: `403 Forbidden` (DENY) - Center 102 attempting to download Exam mapped to Center 101.
- **Valid Center (Proper Tenant)**: `200 OK` (ALLOW) - Center 101 accessing Center 101 paper.
- **Payload Manipulation**: `403 Forbidden` (DENY) - Auditor attempting to forge an upload request.
- **Object Creator Validation**: `403 Forbidden` (DENY) - Setter Eve attempting to access Setter Alice's paper.

*All 7/7 explicit authorization pytests PASSED securely.*

## 16. Problems Encountered
None specific to Day 3. Data isolation strategies integrated cleanly with SQLAlchemy sessions.

## 17. Solutions Applied
Implemented the `ExamCenter` mapping structure as an active relational layer rather than relying on brittle metadata or raw JSON lists, ensuring strong referential integrity.

## 18. Assumptions
The Frontend will properly capture the `storage_object_id` when integrating with R2, while our backend remains the strict arbiter of exactly *who* can access that object ID.

## 19. Limitations
Day 3 focused on standard API tests. Load testing concurrent center downloads and complex hierarchical role inheritance (e.g. if an Admin wants to act as a Setter) is deferred.

## 20. Future Work
Integrate actual Cloudflare R2 bucket signed URLs into the download route now that the authorization boundary is secure.

## 21. Key Concepts Learned
Hardened API security relies on establishing a rigid chain of trust: JWT -> DB User -> DB Role -> DB Permission -> DB Relational Mapping.

## 22. Change Summary
- Created `ExamCenter` model.
- Added `storage_object_id`, `status`, `created_by`, `document_hash` to `Paper`.
- Engineered `has_permission` RBAC matrix.
- Developed `require_permission` and `get_paper_with_object_auth` dependencies.
- Implemented `/exams/papers` (upload) and `/exams/papers/{id}/download` API routes.
- Wrote extensive Object Authorization testing suite.

## 23. Final Summary
Day 3 effectively closes the most critical security vulnerabilities. By isolating authentication from role-permissions and tying those permissions explicitly to trusted, server-side object ownership chains, we ensure that a compromised or malicious client cannot exfiltrate papers assigned to other regions or manipulate administrative workflows.
