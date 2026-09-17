import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, engine, SessionLocal
from backend.users.models import User, Role
from backend.auth.security import get_password_hash

def seed_users():
    db = SessionLocal()
    users = [
        {"email": "setter@test.com", "role": "QUESTION_SETTER"},
        {"email": "reviewer@test.com", "role": "REVIEWER"},
        {"email": "c@test.com", "role": "EXAM_CONTROLLER"},
        {"email": "o@test.com", "role": "EXTERNAL_OBSERVER"},
        {"email": "center@test.com", "role": "CENTER_SUPERINTENDENT"},
        {"email": "auditor@test.com", "role": "AUDITOR"}
    ]
    for u in users:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if not existing:
            role = db.query(Role).filter(Role.name == u["role"]).first()
            new_user = User(
                name="Demo User",
                email=u["email"],
                password_hash=get_password_hash("pass"),
                role_id=role.id,
                is_active=True,
                totp_secret="base32secret3232",
                center_id=101 if u["role"] == "CENTER_SUPERINTENDENT" else None
            )
            db.add(new_user)
    db.commit()
    db.close()
    print("Seeded demo users.")

if __name__ == "__main__":
    seed_users()

def seed_exam():
    db = SessionLocal()
    from backend.exams.models import Exam
    from datetime import datetime, timezone, timedelta
    existing = db.query(Exam).filter(Exam.id == 1).first()
    if not existing:
        new_exam = Exam(
            title="Demo Exam",
            scheduled_date=datetime.now(timezone.utc),
            release_start=datetime.now(timezone.utc) - timedelta(hours=1),
            release_end=datetime.now(timezone.utc) + timedelta(hours=2)
        )
        db.add(new_exam)
        db.commit()
        
        from backend.exams.models import ExamCenter
        new_ec = ExamCenter(exam_id=new_exam.id, center_id=101)
        db.add(new_ec)
        db.commit()
    db.close()
    print("Seeded demo exam.")

if __name__ == "__main__":
    seed_exam()
