import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone

from backend.main import app
from backend.database import Base, get_db
from backend.users.models import User, Role
from backend.exams.models import Exam, Paper, ExamCenter
from backend.auth.security import get_password_hash, create_access_token

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_authz.db"
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


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # 1. Setup Roles
    role_setter = Role(name="QUESTION_SETTER")
    role_center = Role(name="CENTER_SUPERINTENDENT")
    role_auditor = Role(name="AUDITOR")
    db.add_all([role_setter, role_center, role_auditor])
    db.commit()

    # 2. Setup Users
    setter_user = User(
        name="Alice Setter",
        email="alice@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_setter.id,
        is_active=True)

    # Center Superintendent for Center 101
    center_101_user = User(
        name="Bob Center101",
        email="bob@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_center.id,
        center_id=101,
        is_active=True)

    # Center Superintendent for Center 102
    center_102_user = User(
        name="Charlie Center102",
        email="charlie@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_center.id,
        center_id=102,
        is_active=True)

    auditor_user = User(
        name="Dave Auditor",
        email="dave@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_auditor.id,
        is_active=True)
    db.add_all([setter_user, center_101_user, center_102_user, auditor_user])
    db.commit()

    # 3. Setup Exams and assignments
    exam1 = Exam(title="Math 101", scheduled_date=datetime.now(timezone.utc))
    db.add(exam1)
    db.commit()

    # Exam 1 is assigned ONLY to Center 101
    exam1_assignment = ExamCenter(exam_id=exam1.id, center_id=101)
    db.add(exam1_assignment)
    db.commit()

    # 4. Setup Papers
    paper1 = Paper(
        title="Math 101 - Set A",
        exam_id=exam1.id,
        storage_object_id="obj_123",
        created_by=setter_user.id,
        status="approved")
    db.add(paper1)
    db.commit()

    yield
    Base.metadata.drop_all(bind=engine)


def get_token(email: str, role: str, expire_delta=None):
    return create_access_token(
        data={
            "sub": email,
            "role": role},
        expires_delta=expire_delta)


def test_missing_token():
    # Attempting to access protected route without a token
    response = client.get("/exams/papers/1/download")
    assert response.status_code == 401


def test_expired_token():
    # Token expired 1 minute ago
    token = get_token(
        "bob@test.com",
        "CENTER_SUPERINTENDENT",
        timedelta(
            minutes=-1))
    response = client.get("/exams/papers/1/download",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_role():
    # Question Setter tries to download paper (needs CENTER_SUPERINTENDENT)
    token = get_token("alice@test.com", "QUESTION_SETTER")
    response = client.get("/exams/papers/1/download",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "Not enough permissions" in response.json()["detail"]


def test_wrong_center_object_level_denial():
    # Center 102 user tries to access Exam 1 paper (which is assigned to
    # Center 101)
    token = get_token("charlie@test.com", "CENTER_SUPERINTENDENT")
    response = client.get("/exams/papers/1/download",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "Object access denied: Paper not assigned to your center" in response.json()[
        "detail"]


def test_valid_access_center_superintendent():
    # Center 101 user accesses Exam 1 paper (Allowed)
    token = get_token("bob@test.com", "CENTER_SUPERINTENDENT")
    response = client.get("/exams/papers/1/download",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code not in [401, 403]


def test_manipulated_resource_id_in_payload():
    # Auditor tries to upload a paper pretending to be a QUESTION_SETTER
    token = get_token("dave@test.com", "AUDITOR")
    response = client.post("/exams/papers", json={
        "title": "Hacked Paper",
        "exam_id": 1,
        "storage_object_id": "hack",
        "document_hash": "hash"
    }, headers={"Authorization": f"Bearer {token}"})
    # Denied at Role check (does not have UPLOAD_PAPER perm)
    assert response.status_code == 403


def test_question_setter_owns_paper_check():
    # Create another setter
    db = TestingSessionLocal()
    role_setter = db.query(Role).filter(Role.name == "QUESTION_SETTER").first()
    other_setter = User(
        name="Eve Setter",
        email="eve@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_setter.id,
        is_active=True)
    db.add(other_setter)
    db.commit()
    db.close()

    # Eve tries to download a paper (Assume download route had Q_SETTER access for this test scenario,
    # but the download route only allows CENTER_SUPERINTENDENT right now)

    # Let's temporarily override the required permission for the test to demonstrate
    # the second branch of Object Level Auth (creator ownership).

    from backend.auth.rbac import ROLE_PERMISSIONS, PERMISSIONS
    ROLE_PERMISSIONS["QUESTION_SETTER"].add(
        PERMISSIONS["DOWNLOAD_ASSIGNED_PAPER"])

    token = get_token("eve@test.com", "QUESTION_SETTER")
    response = client.get("/exams/papers/1/download",
                          headers={"Authorization": f"Bearer {token}"})

    # Eve does not own Paper 1 (Alice created it)
    assert response.status_code == 403
    assert "You do not own this paper" in response.json()["detail"]

    # Revert perm modification
    ROLE_PERMISSIONS["QUESTION_SETTER"].remove(
        PERMISSIONS["DOWNLOAD_ASSIGNED_PAPER"])


def test_setter_to_release_endpoint():
    token = get_token("alice@test.com", "QUESTION_SETTER")
    response = client.post(
        "/release/sessions",
        json={
            "exam_id": 1},
        headers={
            "Authorization": f"Bearer {token}"})
    # Setter does not have the INITIALIZE_RELEASE_SESSION permission
    assert response.status_code == 403
    assert "Not authorized to create release session" in response.json()["detail"]
