"""
File Overview:
This file defines the strict Role-Based Access Control (RBAC) matrix for the system.

Important Objects:
- `ROLE_PERMISSIONS`: A dictionary mapping each role to a set of permitted actions.

Why it is required:
Instead of hardcoding roles in every route, routes can check if a role possesses
a specific permission (e.g., 'upload_paper'). This decoupling makes the RBAC system scalable.
"""

# Define available permissions in the system
PERMISSIONS = {
    "UPLOAD_PAPER": "upload_paper",
    "REVIEW_PAPER": "review_paper",
    "AUTHORIZE_RELEASE": "authorize_release",
    "DOWNLOAD_ASSIGNED_PAPER": "download_assigned_paper",
    "VIEW_AUDIT_DATA": "view_audit_data",
}

# Strict Role-to-Permissions Mapping
ROLE_PERMISSIONS = {
    "QUESTION_SETTER": {
        PERMISSIONS["UPLOAD_PAPER"],
    },
    "REVIEWER": {
        PERMISSIONS["REVIEW_PAPER"],
    },
    "EXAM_CONTROLLER": {
        PERMISSIONS["AUTHORIZE_RELEASE"],
    },
    "EXTERNAL_OBSERVER": {
        PERMISSIONS["AUTHORIZE_RELEASE"],
    },
    "CENTER_SUPERINTENDENT": {
        PERMISSIONS["DOWNLOAD_ASSIGNED_PAPER"],
    },
    "AUDITOR": {
        PERMISSIONS["VIEW_AUDIT_DATA"],
    },
}

def has_permission(role_name: str, permission: str) -> bool:
    """
    Checks if a given role has the specified permission.
    """
    return permission in ROLE_PERMISSIONS.get(role_name, set())
