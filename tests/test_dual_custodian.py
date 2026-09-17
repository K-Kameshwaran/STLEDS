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
from backend.exams.models import Exam, ExamCenter, Paper
from backend.release.models import ReleaseSession, ReleaseAuthorization
from backend.auth.security import get_password_hash, create_access_token

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_dual_auth.db"
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
    # Setup Moto for KMS
    with mock_aws():
        kms = boto3.client("kms", region_name="us-east-1")
        # Create a mock KMS key
        key = kms.create_key(Description="Mock Key for stleds")
        key_id = key["KeyMetadata"]["KeyId"]

        # Override the KMS Client key via environment so the app uses the mock
        # key
        import os
        os.environ["APP_KMS_KEY_ID"] = key_id

        # Setup Database
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()

        role_controller = Role(name="EXAM_CONTROLLER")
        role_observer = Role(name="EXTERNAL_OBSERVER")
        role_setter = Role(name="QUESTION_SETTER")
        role_center = Role(name="CENTER_SUPERINTENDENT")
        db.add_all([role_controller, role_observer, role_setter, role_center])
        db.commit()

        controller = User(
            name="C",
            email="c@test.com",
            password_hash="pass",
            role_id=role_controller.id,
            is_active=True)
        observer = User(
            name="O",
            email="o@test.com",
            password_hash="pass",
            role_id=role_observer.id,
            is_active=True)
        setter = User(
            name="S",
            email="s@test.com",
            password_hash="pass",
            role_id=role_setter.id,
            is_active=True)
        db.add_all([controller, observer, setter])
        db.commit()

        exam1 = Exam(title="Math", scheduled_date=datetime.now(timezone.utc))
        exam2 = Exam(
            title="Physics",
            scheduled_date=datetime.now(
                timezone.utc))
        db.add_all([exam1, exam2])
        db.commit()

        db.close()

        yield


def get_token(email: str, role: str):
    return create_access_token(data={"sub": email, "role": role})


def upload_paper(client: TestClient, setter_token: str, exam_id: int):
    pdf_content = b"%PDF-1.4\n%Fake"
    files = {"file": ("test_paper.pdf", pdf_content, "application/pdf")}
    data = {"title": "Secure Paper", "exam_id": exam_id}
    response = client.post(
        "/exams/papers",
        data=data,
        files=files,
        headers={
            "Authorization": f"Bearer {setter_token}"})
    if response.status_code != 201:
        print("Upload failed:", response.text)
    assert response.status_code == 201
    return response.json()["paper_id"]


def create_release_session(client: TestClient, token: str, exam_id: int):
    res = client.post(
        "/release/sessions",
        json={
            "exam_id": exam_id},
        headers={
            "Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    return res.json()["session_id"]


def authorize_session(
        client: TestClient,
        token: str,
        session_id: int,
        offset_minutes: int = 0):
    client_time = (datetime.now(timezone.utc) +
                   timedelta(minutes=offset_minutes)).isoformat()
    return client.post(
        f"/release/sessions/{session_id}/authorize",
        json={"client_timestamp": client_time},
        headers={"Authorization": f"Bearer {token}"}
    )


def execute_session(client: TestClient, token: str, session_id: int):
    return client.post(
        f"/release/sessions/{session_id}/execute",
        headers={
            "Authorization": f"Bearer {token}"})


def test_dual_custodian_success():
    setter_token = get_token("s@test.com", "QUESTION_SETTER")
    controller_token = get_token("c@test.com", "EXAM_CONTROLLER")
    observer_token = get_token("o@test.com", "EXTERNAL_OBSERVER")

    # Upload paper (creates shares)
    upload_paper(client, setter_token, 1)

    # Create Session
    session_id = create_release_session(client, controller_token, 1)

    # Custodian A authorizes
    res_a = authorize_session(client, controller_token, session_id)
    assert res_a.status_code == 200

    # Custodian B authorizes
    res_b = authorize_session(client, observer_token, session_id)
    assert res_b.status_code == 200

    # Execute (Both present)
    res_exec = execute_session(client, controller_token, session_id)
    assert res_exec.status_code == 200
    assert "successfully" in res_exec.json()["message"]


def test_controller_only_deny():
    setter_token = get_token("s@test.com", "QUESTION_SETTER")
    controller_token = get_token("c@test.com", "EXAM_CONTROLLER")

    upload_paper(client, setter_token, 1)
    session_id = create_release_session(client, controller_token, 1)

    # Custodian A only
    authorize_session(client, controller_token, session_id)

    # Execute should fail closed
    res_exec = execute_session(client, controller_token, session_id)
    assert res_exec.status_code == 403
    assert "Insufficient custodian authorization material" in res_exec.json()[
        "detail"]


def test_observer_only_deny():
    setter_token = get_token("s@test.com", "QUESTION_SETTER")
    observer_token = get_token("o@test.com", "EXTERNAL_OBSERVER")

    upload_paper(client, setter_token, 1)
    session_id = create_release_session(
        client, observer_token, 1)  # Anyone can create

    # Custodian B only
    authorize_session(client, observer_token, session_id)

    res_exec = execute_session(client, observer_token, session_id)
    assert res_exec.status_code == 403
    assert "Insufficient custodian authorization material" in res_exec.json()[
        "detail"]


def test_replay_protection_consumed_authorization():
    setter_token = get_token("s@test.com", "QUESTION_SETTER")
    controller_token = get_token("c@test.com", "EXAM_CONTROLLER")
    observer_token = get_token("o@test.com", "EXTERNAL_OBSERVER")

    upload_paper(client, setter_token, 1)
    session_id = create_release_session(client, controller_token, 1)

    authorize_session(client, controller_token, session_id)
    authorize_session(client, observer_token, session_id)

    # First execution succeeds
    res_exec_1 = execute_session(client, controller_token, session_id)
    assert res_exec_1.status_code == 200

    # Second execution should fail because authorizations are consumed and
    # session is active
    res_exec_2 = execute_session(client, controller_token, session_id)
    assert res_exec_2.status_code == 400
    assert "already executed" in res_exec_2.json()["detail"]


def test_replay_protection_stale_timestamp():
    controller_token = get_token("c@test.com", "EXAM_CONTROLLER")
    session_id = create_release_session(client, controller_token, 1)

    # Submit authorization with a timestamp from 10 minutes ago
    res = authorize_session(
        client,
        controller_token,
        session_id,
        offset_minutes=-10)
    assert res.status_code == 400
    assert "stale or invalid" in res.json()["detail"]


def test_wrong_role_deny():
    setter_token = get_token("s@test.com", "QUESTION_SETTER")
    controller_token = get_token("c@test.com", "EXAM_CONTROLLER")
    session_id = create_release_session(client, controller_token, 1)

    # Setter attempts to authorize
    res = authorize_session(client, setter_token, session_id)
    assert res.status_code == 403
    assert "Role not authorized" in res.json()["detail"]
