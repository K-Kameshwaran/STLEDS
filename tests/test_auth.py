import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import timedelta
import time
import pyotp

from backend.main import app
from backend.database import Base, get_db
from backend.users.models import User, Role
from backend.auth.security import get_password_hash, create_access_token

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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

    # Create roles
    role_standard = Role(name="REVIEWER")
    role_admin = Role(name="EXAM_CONTROLLER")
    db.add(role_standard)
    db.add(role_admin)
    db.commit()

    # Create valid active user
    valid_user = User(
        name="Valid User",
        email="valid@example.com",
        password_hash=get_password_hash("password123"),
        role_id=role_standard.id,
        is_active=True
    )

    # Create inactive user
    inactive_user = User(
        name="Inactive User",
        email="inactive@example.com",
        password_hash=get_password_hash("password123"),
        role_id=role_standard.id,
        is_active=False
    )

    # Create MFA user
    mfa_secret = pyotp.random_base32()
    mfa_user = User(
        name="MFA User",
        email="mfa@example.com",
        password_hash=get_password_hash("password123"),
        role_id=role_admin.id,
        is_active=True,
        totp_secret=mfa_secret
    )

    db.add_all([valid_user, inactive_user, mfa_user])
    db.commit()

    yield

    # Teardown
    Base.metadata.drop_all(bind=engine)


def test_login_valid_credentials():
    response = client.post("/auth/login", json={
        "email": "valid@example.com",
        "password": "password123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_invalid_password():
    response = client.post("/auth/login", json={
        "email": "valid@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_unknown_user():
    response = client.post("/auth/login", json={
        "email": "unknown@example.com",
        "password": "password123"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_inactive_user():
    response = client.post("/auth/login", json={
        "email": "inactive@example.com",
        "password": "password123"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Account is inactive"


def test_mfa_required_for_exam_controller():
    # Login without MFA code
    response = client.post("/auth/login", json={
        "email": "mfa@example.com",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["mfa_required"]
    assert data["access_token"] == ""


def test_mfa_login_success():
    # We need the secret to generate a valid code
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "mfa@example.com").first()
    db.close()

    totp = pyotp.TOTP(user.totp_secret)
    valid_code = totp.now()

    response = client.post("/auth/login", json={
        "email": "mfa@example.com",
        "password": "password123",
        "mfa_code": valid_code
    })
    assert response.status_code == 200
    data = response.json()
    assert data["mfa_required"] == False
    assert "access_token" in data


def test_mfa_login_invalid_code():
    response = client.post("/auth/login", json={
        "email": "mfa@example.com",
        "password": "password123",
        "mfa_code": "000000"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid MFA code"


def test_expired_token():
    # Create an artificially expired token
    expired_token = create_access_token(
        data={"sub": "valid@example.com", "role": "REVIEWER"},
        expires_delta=timedelta(seconds=-1)
    )

    from backend.auth.dependencies import get_current_user
    from fastapi import HTTPException

    # We can test the dependency directly or via a mock endpoint.
    # Since we don't have a protected endpoint in main yet, we'll create a
    # temporary one for testing.

    app.get("/test-protected")(lambda current_user=__import__(
        'fastapi').Depends(get_current_user): {"status": "ok"})

    response = client.get(
        "/test-protected",
        headers={
            "Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
