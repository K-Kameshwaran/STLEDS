"""
File Overview:
This script initializes the database tables and seeds the required roles.

Important Functions:
- `init_db()`: Creates all database tables defined in the SQLAlchemy metadata.
- `seed_roles()`: Populates the `roles` table with the required Day 2 roles.
"""

from backend.database import engine, SessionLocal, Base
from backend.users.models import Role, User
from backend.exams.models import Exam, Paper, Approval, ExamCenter
from backend.release.models import ReleaseSession
from backend.crypto.models import KeyMetadata
from backend.audit.models import AuditLog

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

def seed_roles():
    """
    Why it is needed:
    The application logic (and authentication) depends on these specific roles existing.
    We seed them during database setup.
    """
    roles = [
        "QUESTION_SETTER",
        "REVIEWER",
        "EXAM_CONTROLLER",
        "EXTERNAL_OBSERVER",
        "CENTER_SUPERINTENDENT",
        "AUDITOR"
    ]
    
    db = SessionLocal()
    try:
        for role_name in roles:
            existing_role = db.query(Role).filter(Role.name == role_name).first()
            if not existing_role:
                new_role = Role(name=role_name)
                db.add(new_role)
                print(f"Added role: {role_name}")
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    seed_roles()
    print("Database setup complete.")
