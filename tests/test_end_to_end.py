import pytest
import os
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from moto import mock_aws
import boto3

from backend.main import app
from backend.database import Base, get_db
from backend.users.models import User, Role
from backend.exams.models import Exam, ExamCenter, Paper
from backend.release.models import ReleaseSession
from backend.auth.security import get_password_hash
from backend.audit.models import AuditLog
from backend.audit.service import verify_audit_chain

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_e2e.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False})
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def set_dependency_override():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


client = TestClient(app)

from backend.auth.security import create_access_token
def get_token(email: str, role: str):
    return create_access_token(data={"sub": email, "role": role})



@pytest.fixture(scope="module", autouse=True)
def setup_database_and_kms():
    with mock_aws():
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        
        kms = boto3.client("kms", region_name="us-east-1")
        key = kms.create_key(Description="Mock Key for stleds e2e tests")
        os.environ["APP_KMS_KEY_ID"] = key["KeyMetadata"]["KeyId"]

        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()

        # Setup Roles
        role_setter = Role(name="QUESTION_SETTER")
        role_reviewer = Role(name="REVIEWER")
        role_controller = Role(name="EXAM_CONTROLLER")
        role_observer = Role(name="EXTERNAL_OBSERVER")
        role_center = Role(name="CENTER_SUPERINTENDENT")
        db.add_all([role_setter,
                    role_reviewer,
                    role_controller,
                    role_observer,
                    role_center])
        db.commit()

        # Setup Users
        users = [
            User(
                name="Setter",
                email="setter@test.com",
                password_hash=get_password_hash("pass"),
                role_id=role_setter.id,
                is_active=True),
            User(
                name="Reviewer",
                email="reviewer@test.com",
                password_hash=get_password_hash("pass"),
                role_id=role_reviewer.id,
                is_active=True),
            User(
                name="Controller",
                email="controller@test.com",
                password_hash=get_password_hash("pass"),
                role_id=role_controller.id,
                is_active=True),
            User(
                name="Observer",
                email="observer@test.com",
                password_hash=get_password_hash("pass"),
                role_id=role_observer.id,
                is_active=True),
            User(
                name="Center 101",
                email="center@test.com",
                password_hash=get_password_hash("pass"),
                role_id=role_center.id,
                center_id=101,
                is_active=True)]
        db.add_all(users)
        db.commit()

        # Setup Exam inside window
        now = datetime.now(timezone.utc)
        exam = Exam(
            title="E2E Exam",
            scheduled_date=now,
            release_start=now - timedelta(hours=1),
            release_end=now + timedelta(hours=1)
        )
        db.add(exam)
        db.commit()
        db.add(ExamCenter(exam_id=exam.id, center_id=101))
        db.commit()

        db.close()
        yield
        Base.metadata.drop_all(bind=engine)


def test_full_e2e_lifecycle():
    # 1. Login
    res = client.post(
        "/auth/login",
        json={
            "email": "setter@test.com",
            "password": "pass", "mfa_code": "123456"})
    assert res.status_code == 200
    setter_token = res.json()["access_token"]

    # 2. Upload -> Encrypt -> Store
    import io
    from reportlab.pdfgen import canvas
    packet = io.BytesIO()
    c = canvas.Canvas(packet)
    c.drawString(100, 100, "Secure Content")
    c.save()
    pdf_content = packet.getvalue()

    res = client.post(
        "/exams/papers",
        data={
            "title": "E2E Paper",
            "exam_id": 1},
        files={
            "file": (
                "test.pdf",
                pdf_content,
                "application/pdf")},
        headers={
            "Authorization": f"Bearer {setter_token}"})
    assert res.status_code == 201
    paper_id = res.json()["paper_id"]

    # 3. Review -> Approve
    reviewer_token = get_token("reviewer@test.com", "REVIEWER")

    res_rev = client.post(
        f"/exams/papers/{paper_id}/status?new_status=PENDING_REVIEW",
        headers={
            "Authorization": f"Bearer {reviewer_token}"})
    assert res_rev.status_code == 200

    res = client.post(
        f"/exams/papers/{paper_id}/status?new_status=APPROVED",
        headers={
            "Authorization": f"Bearer {reviewer_token}"})
    assert res.status_code == 200

    controller_token = get_token("controller@test.com", "EXAM_CONTROLLER")

    res = client.post(
        f"/exams/papers/{paper_id}/status?new_status=LOCKED",
        headers={
            "Authorization": f"Bearer {controller_token}"})
    assert res.status_code == 200

    # 4. Attempt early release (Denied)
    # Controller tries to download directly
    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {controller_token}"})
    assert res.status_code == 403  # Only CS can download

    # 5. Complete dual authorization
    observer_token = get_token("observer@test.com", "EXTERNAL_OBSERVER")

    res_s = client.post(
        "/release/sessions",
        json={
            "exam_id": 1},
        headers={
            "Authorization": f"Bearer {controller_token}"})
    session_id = res_s.json()["session_id"]

    now = datetime.now(timezone.utc)
    client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {controller_token}"})
    client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {observer_token}"})

    # 6. Release
    res = client.post(
        f"/release/sessions/{session_id}/execute",
        headers={
            "Authorization": f"Bearer {controller_token}"})
    assert res.status_code == 200

    # 7. Center download & Watermark
    res = client.post(
        "/auth/login",
        json={
            "email": "center@test.com",
            "password": "pass", "mfa_code": "123456"})
    center_token = res.json()["access_token"]

    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {center_token}"})
    assert res.status_code == 200
    assert len(res.content) > len(pdf_content)  # Watermark added

    # 8. Audit Verification
    db = TestingSessionLocal()
    audit_res = verify_audit_chain(db)
    assert audit_res["valid"] is True

    # 9. Modify historical record
    record = db.query(AuditLog).order_by(AuditLog.id).first()
    record.action = "TAMPERED"
    db.commit()

    # 10. Audit Verification (Tamper Detected)
    audit_res2 = verify_audit_chain(db)
    assert audit_res2["valid"] is False
    assert audit_res2["first_invalid_record"] == record.id
    db.close()
