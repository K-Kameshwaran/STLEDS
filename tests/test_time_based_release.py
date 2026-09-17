import os
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from moto import mock_aws
import boto3

from backend.main import app
from backend.database import Base, get_db
from backend.users.models import User, Role
from backend.exams.models import Exam, Paper
from backend.release.models import ReleaseSession, ReleaseAuthorization
from backend.auth.security import get_password_hash, create_access_token
from backend.release.state_machine import PaperState

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_time_release.db"
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


@pytest.fixture(scope="function", autouse=True)
def setup_database_and_kms():
    with mock_aws():
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        
        kms = boto3.client("kms", region_name="us-east-1")
        key = kms.create_key(Description="Mock Key for stleds time tests")
        os.environ["APP_KMS_KEY_ID"] = key["KeyMetadata"]["KeyId"]

        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()

        roles = [
            Role(name="EXAM_CONTROLLER"),
            Role(name="EXTERNAL_OBSERVER"),
            Role(name="QUESTION_SETTER"),
            Role(name="CENTER_SUPERINTENDENT")
        ]
        db.add_all(roles)
        db.commit()

        users = [
            User(
                name="C",
                email="c@test.com",
                password_hash="pass",
                role_id=roles[0].id,
                is_active=True),
            User(
                name="O",
                email="o@test.com",
                password_hash="pass",
                role_id=roles[1].id,
                is_active=True),
            User(
                name="S",
                email="s@test.com",
                password_hash="pass",
                role_id=roles[2].id,
                is_active=True),
            User(
                name="CS",
                email="cs@test.com",
                password_hash="pass",
                role_id=roles[3].id,
                is_active=True,
                center_id=1),
        ]
        db.add_all(users)
        db.commit()

        now = datetime.now(timezone.utc)

        # We will create an exam and manipulate its time dynamically in the
        # tests rather than mocking time
        exam = Exam(
            title="Time Exam",
            scheduled_date=now,
            # Initially, set the window to [now - 1h, now + 1h] so it's
            # currently INSIDE
            release_start=now - timedelta(hours=1),
            release_end=now + timedelta(hours=1)
        )
        db.add(exam)
        db.commit()

        # Day 6 tests fix: Assign Exam to Center 1
        from backend.exams.models import ExamCenter
        db.add(ExamCenter(exam_id=exam.id, center_id=1))
        db.commit()
        db.close()
        yield


def get_token(email: str, role: str):
    return create_access_token(data={"sub": email, "role": role})


def setup_authorized_paper(
        db_session,
        exam_id=1,
        time_offset="inside",
        status=PaperState.LOCKED):
    """
    Sets up a fully authorized paper in the database.
    time_offset: "before", "inside", "after"
    status: Paper's database status
    """
    now = datetime.now(timezone.utc)

    exam = db_session.query(Exam).filter(Exam.id == exam_id).first()
    if time_offset == "before":
        exam.release_start = now + timedelta(hours=1)
        exam.release_end = now + timedelta(hours=2)
    elif time_offset == "inside":
        exam.release_start = now - timedelta(hours=1)
        exam.release_end = now + timedelta(hours=1)
    elif time_offset == "after":
        exam.release_start = now - timedelta(hours=2)
        exam.release_end = now - timedelta(hours=1)

    setter_token = get_token("s@test.com", "QUESTION_SETTER")

    # Generate a valid minimalistic PDF for pypdf to parse
    import io
    from reportlab.pdfgen import canvas
    packet = io.BytesIO()
    c = canvas.Canvas(packet)
    c.drawString(100, 100, "Original Content")
    c.save()
    pdf_content = packet.getvalue()

    res = client.post(
        "/exams/papers",
        data={"title": "Test Paper", "exam_id": exam_id},
        files={"file": ("test.pdf", pdf_content, "application/pdf")},
        headers={"Authorization": f"Bearer {setter_token}"}
    )
    assert res.status_code == 201
    paper_id = res.json()["paper_id"]

    # Transition the state manually for the test
    paper = db_session.query(Paper).filter(Paper.id == paper_id).first()
    paper.status = status
    db_session.commit()

    # Authorize it via Dual Custodian
    c_token = get_token("c@test.com", "EXAM_CONTROLLER")
    o_token = get_token("o@test.com", "EXTERNAL_OBSERVER")

    res_s = client.post(
        "/release/sessions",
        json={
            "exam_id": exam_id},
        headers={
            "Authorization": f"Bearer {c_token}"})
    session_id = res_s.json()["session_id"]

    client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {c_token}"})
    client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {o_token}"})
    client.post(
        f"/release/sessions/{session_id}/execute",
        headers={
            "Authorization": f"Bearer {c_token}"})

    return paper_id, len(pdf_content)


def test_time_state_inside_window_allow():
    db = TestingSessionLocal()
    paper_id, original_len = setup_authorized_paper(
        db, time_offset="inside", status=PaperState.LOCKED)
    db.close()

    cs_token = get_token("cs@test.com", "CENTER_SUPERINTENDENT")
    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {cs_token}"})
    assert res.status_code == 200

    # Verify the watermark was applied by checking the file length is significantly different
    # and the output is a valid PDF containing watermark strings (in its byte
    # streams)
    assert len(res.content) > original_len
    # pypdf compression might hide raw strings, but we ensure length changed
    assert b"EXAMINATION PAPER" in res.content or b"EXAM ID" in res.content


def test_time_state_before_window_deny():
    db = TestingSessionLocal()
    paper_id, _ = setup_authorized_paper(
        db, time_offset="before", status=PaperState.LOCKED)
    db.close()

    cs_token = get_token("cs@test.com", "CENTER_SUPERINTENDENT")
    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {cs_token}"})
    assert res.status_code == 403
    assert "not in RELEASE_WINDOW state" in res.json()["detail"]
    assert "LOCKED" in res.json()["detail"]


def test_time_state_after_window_deny():
    db = TestingSessionLocal()
    paper_id, _ = setup_authorized_paper(
        db, time_offset="after", status=PaperState.LOCKED)
    db.close()

    cs_token = get_token("cs@test.com", "CENTER_SUPERINTENDENT")
    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {cs_token}"})
    assert res.status_code == 403
    assert "not in RELEASE_WINDOW state" in res.json()["detail"]
    assert "EXPIRED" in res.json()["detail"]


def test_unapproved_paper_deny():
    db = TestingSessionLocal()
    # Inside window, authorized, but paper is only in PENDING_REVIEW state
    # (not LOCKED yet)
    paper_id, _ = setup_authorized_paper(
        db, time_offset="inside", status=PaperState.PENDING_REVIEW)
    db.close()

    cs_token = get_token("cs@test.com", "CENTER_SUPERINTENDENT")
    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {cs_token}"})
    assert res.status_code == 403
    assert "not in RELEASE_WINDOW state" in res.json()["detail"]
    assert "PENDING_REVIEW" in res.json()["detail"]


def test_invalid_state_transition():
    c_token = get_token("c@test.com", "EXAM_CONTROLLER")
    db = TestingSessionLocal()
    paper_id, _ = setup_authorized_paper(
        db, time_offset="inside", status=PaperState.ENCRYPTED)
    db.close()

    # Try jumping directly from ENCRYPTED to LOCKED
    res = client.post(
        f"/exams/papers/{paper_id}/status?new_status=LOCKED",
        headers={
            "Authorization": f"Bearer {c_token}"})
    assert res.status_code == 400
    assert "Invalid transition" in res.json()["detail"]


def test_wrong_center_deny():
    # Setup a new paper assigned to exam 1, which is assigned to Center 1
    db = TestingSessionLocal()
    paper_id, _ = setup_authorized_paper(
        db, time_offset="inside", status=PaperState.LOCKED)

    # Create a malicious CS assigned to Center 2
    roles = db.query(Role).all()
    cs_role = next(r for r in roles if r.name == "CENTER_SUPERINTENDENT")
    malicious_cs = User(
        name="CS2",
        email="cs2@test.com",
        password_hash="pass",
        role_id=cs_role.id,
        is_active=True,
        center_id=2)
    db.add(malicious_cs)
    db.commit()
    db.close()

    cs2_token = get_token("cs2@test.com", "CENTER_SUPERINTENDENT")
    res = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {cs2_token}"})
    assert res.status_code == 403
    assert "not assigned to your center" in res.json()["detail"]


def test_inside_release_window_one_custodian():
    now = datetime.now(timezone.utc)
    c_token = get_token("c@test.com", "EXAM_CONTROLLER")

    # Initialize session
    res_s = client.post(
        "/release/sessions",
        json={
            "exam_id": 1},
        headers={
            "Authorization": f"Bearer {c_token}"})
    session_id = res_s.json()["session_id"]

    # Only Controller authorizes
    client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {c_token}"})

    # Try to execute
    res = client.post(
        f"/release/sessions/{session_id}/execute",
        headers={
            "Authorization": f"Bearer {c_token}"})
    assert res.status_code == 403
    assert "Insufficient custodian authorization material" in res.json()[
        "detail"]


def test_replayed_authorization():
    now = datetime.now(timezone.utc)
    c_token = get_token("c@test.com", "EXAM_CONTROLLER")

    res_s = client.post(
        "/release/sessions",
        json={
            "exam_id": 1},
        headers={
            "Authorization": f"Bearer {c_token}"})
    session_id = res_s.json()["session_id"]

    # Authorize once
    res1 = client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {c_token}"})
    assert res1.status_code == 200

    # Authorize again (Replay)
    res2 = client.post(
        f"/release/sessions/{session_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {c_token}"})
    assert res2.status_code == 400
    assert "Active authorization already exists" in res2.json()["detail"]


def test_wrong_examination():
    # Attempting to authorize a different exam
    now = datetime.now(timezone.utc)
    c_token = get_token("c@test.com", "EXAM_CONTROLLER")

    # Create Exam 2
    db = TestingSessionLocal()
    exam2 = Exam(title="Exam 2", scheduled_date=now)
    db.add(exam2)
    db.commit()
    exam2_id = exam2.id
    db.close()

    # Session for Exam 1
    res_s = client.post(
        "/release/sessions",
        json={
            "exam_id": 1},
        headers={
            "Authorization": f"Bearer {c_token}"})
    session_id = res_s.json()["session_id"]

    # What if a user tries to modify the exam ID? The session is tied to exam 1 in the backend.
    # But let's say they create a session for Exam 2, and try to use it for
    # Exam 1 paper.
    res_s2 = client.post(
        "/release/sessions",
        json={
            "exam_id": exam2_id},
        headers={
            "Authorization": f"Bearer {c_token}"})
    session2_id = res_s2.json()["session_id"]

    o_token = get_token("o@test.com", "EXTERNAL_OBSERVER")
    client.post(
        f"/release/sessions/{session2_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {c_token}"})
    client.post(
        f"/release/sessions/{session2_id}/authorize",
        json={
            "client_timestamp": now.isoformat()},
        headers={
            "Authorization": f"Bearer {o_token}"})
    client.post(
        f"/release/sessions/{session2_id}/execute",
        headers={
            "Authorization": f"Bearer {c_token}"})

    # The session is active, BUT for exam 2.
    # A paper for Exam 1 should NOT be downloadable if the active session is
    # for Exam 2.

    # Create an exam 1 paper directly and set to LOCKED
    db = TestingSessionLocal()
    paper1, _ = setup_authorized_paper(
        db, exam_id=1, time_offset="inside", status=PaperState.LOCKED)

    # The `setup_authorized_paper` actually authorizes Exam 1 session.
    # Let's bypass it: just change its status to LOCKED and ensure Exam 1 has
    # NO active session.
    db.query(ReleaseSession).filter(ReleaseSession.exam_id == 1).delete()
    db.commit()
    db.close()

    cs_token = get_token("cs@test.com", "CENTER_SUPERINTENDENT")
    # Exam 1 has NO active session, but Exam 2 DOES have an active session
    res = client.get(
        f"/exams/papers/{paper1}/download",
        headers={
            "Authorization": f"Bearer {cs_token}"})
    assert res.status_code == 403
    assert "Dual-custodian authorization missing or incomplete" in res.json()["detail"]
