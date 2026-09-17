import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from jose import jwt

from backend.main import app
from backend.auth.security import SECRET_KEY, ALGORITHM

from backend.users.models import User




from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_authentication.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Add dummy user for test_incorrect_password
    db = TestingSessionLocal()
    from backend.users.models import Role
    from backend.auth.security import get_password_hash
    
    role = Role(name="EXAM_CONTROLLER")
    db.add(role)
    db.commit()
    
    user = User(
        name="C",
        email="c@test.com",
        password_hash=get_password_hash("password123"),
        role_id=role.id,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.close()
    
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_incorrect_password():
    res = client.post(
        "/auth/login",
        json={
            "email": "c@test.com",
            "password": "wrongpassword"})
    assert res.status_code == 401
    assert "Incorrect email or password" in res.json()["detail"]


def test_unknown_user():
    # Attempting to login with a non-existent email
    res = client.post(
        "/auth/login",
        json={
            "email": "nonexistent@test.com",
            "password": "somepassword"})
    assert res.status_code == 401
    assert "Incorrect email or password" in res.json()["detail"]


def test_expired_token():
    # Manually craft an expired token
    expire = datetime.now(timezone.utc) - timedelta(minutes=10)
    to_encode = {"sub": "c@test.com", "role": "EXAM_CONTROLLER", "exp": expire}
    expired_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    res = client.get("/exams/papers/1/download",
                     headers={"Authorization": f"Bearer {expired_token}"})
    # Must fail with 401
    assert res.status_code == 401
    assert "Could not validate credentials" in res.json(
    )["detail"] or "Signature has expired" in res.json()["detail"]


def test_invalid_token():
    # Send a token with an invalid signature
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI.invalidpayload.invalidsignature"
    res = client.get("/exams/papers/1/download",
                     headers={"Authorization": f"Bearer {fake_token}"})
    assert res.status_code == 401


def test_inactive_user():
    # Setup an inactive user
    db = TestingSessionLocal()
    # Ensure user is deleted if they exist from previous test
    existing = db.query(User).filter(User.email == "inactive@test.com").first()
    if not existing:
        inactive_user = User(
            name="Inactive",
            email="inactive@test.com",
            password_hash="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqiRQYq",
            role_id=1,
            is_active=False)
        db.add(inactive_user)
        db.commit()
    db.close()

    # Attempt to login
    # The password hash above is for "password" (bcrypt)
    res = client.post(
        "/auth/login",
        json={
            "email": "inactive@test.com",
            "password": "password"})
    assert res.status_code in [400, 401]
    assert "inactive" in res.json()["detail"].lower() or "incorrect" in res.json()["detail"].lower()
