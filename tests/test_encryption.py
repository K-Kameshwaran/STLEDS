import pytest
import os
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta

from backend.main import app
from backend.database import Base, get_db
from backend.users.models import User, Role
from backend.exams.models import Exam, ExamCenter, Paper
from backend.auth.security import get_password_hash, create_access_token
from backend.storage.r2 import STORAGE_DIR
from backend.crypto.engine import encrypt_document, decrypt_document, generate_key, generate_nonce
from backend.crypto.kms import unwrap_key
from cryptography.exceptions import InvalidTag

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_crypto.db"
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
    import boto3
    from moto import mock_aws
    with mock_aws():
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        
        kms = boto3.client("kms", region_name="us-east-1")
        key = kms.create_key(Description="Mock Key")
        os.environ["APP_KMS_KEY_ID"] = key["KeyMetadata"]["KeyId"]

        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()

        # 1. Setup Roles
        role_setter = Role(name="QUESTION_SETTER")
        role_center = Role(name="CENTER_SUPERINTENDENT")
        db.add_all([role_setter, role_center])
        db.commit()

        # 2. Setup Users
        setter_user = User(
        name="Alice Setter",
        email="alice_crypto@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_setter.id,
        is_active=True)

        center_user = User(
        name="Bob Center",
        email="bob_crypto@test.com",
        password_hash=get_password_hash("pass"),
        role_id=role_center.id,
        center_id=101,
        is_active=True)
        db.add_all([setter_user, center_user])
        db.commit()

        # 3. Setup Exams and assignments
        exam1 = Exam(
        title="Crypto Exam",
        scheduled_date=datetime.now(
            timezone.utc))
        db.add(exam1)
        db.commit()

        exam1_assignment = ExamCenter(exam_id=exam1.id, center_id=101)
        db.add(exam1_assignment)
        db.commit()

        yield
        Base.metadata.drop_all(bind=engine)


def get_token(email: str, role: str):
    return create_access_token(data={"sub": email, "role": role})


def test_end_to_end_upload_and_download():
    # 1. Upload via QUESTION_SETTER
    setter_token = get_token("alice_crypto@test.com", "QUESTION_SETTER")

    import io
    from reportlab.pdfgen import canvas
    packet = io.BytesIO()
    c = canvas.Canvas(packet)
    c.drawString(100, 100, "Secure Content")
    c.save()
    pdf_content = packet.getvalue()

    files = {"file": ("test_paper.pdf", pdf_content, "application/pdf")}
    data = {"title": "Secure Exam Paper", "exam_id": 1}

    response = client.post(
        "/exams/papers",
        data=data,
        files=files,
        headers={
            "Authorization": f"Bearer {setter_token}"})
    assert response.status_code == 201
    paper_id = response.json()["paper_id"]

    # Bypass authorization for encryption test
    db = TestingSessionLocal()
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    paper.status = "LOCKED"
    
    from backend.release.models import ReleaseSession
    session = ReleaseSession(exam_id=1, status="active", started_at=datetime.now(timezone.utc))
    db.add(session)
    
    exam = db.query(Exam).filter(Exam.id == 1).first()
    exam.release_start = datetime.now(timezone.utc) - timedelta(hours=1)
    exam.release_end = datetime.now(timezone.utc) + timedelta(hours=1)
    
    db.commit()
    db.close()

    # 2. Download via CENTER_SUPERINTENDENT
    center_token = get_token("bob_crypto@test.com", "CENTER_SUPERINTENDENT")
    response_download = client.get(
        f"/exams/papers/{paper_id}/download",
        headers={
            "Authorization": f"Bearer {center_token}"})

    assert response_download.status_code == 200
    assert len(response_download.content) > len(pdf_content)


def test_raw_storage_verification():
    # Verify that the actual file stored in the R2 mock is NOT the plaintext
    # PDF
    db = TestingSessionLocal()
    paper = db.query(Paper).filter(Paper.title == "Secure Exam Paper").first()
    db.close()

    file_path = os.path.join(STORAGE_DIR, paper.storage_object_id)
    assert os.path.exists(file_path)

    with open(file_path, "rb") as f:
        raw_data = f.read()

    # The raw data should NOT start with PDF magic bytes
    assert not raw_data.startswith(b"%PDF-")

    # The raw data should be significantly different/encrypted
    import io
    from reportlab.pdfgen import canvas
    packet = io.BytesIO()
    c = canvas.Canvas(packet)
    c.drawString(100, 100, "Secure Content")
    c.save()
    pdf_content = packet.getvalue()
    assert raw_data != pdf_content


def test_cryptographic_tampering_modified_ciphertext():
    db = TestingSessionLocal()
    paper = db.query(Paper).filter(Paper.title == "Secure Exam Paper").first()
    db.close()

    file_path = os.path.join(STORAGE_DIR, paper.storage_object_id)
    with open(file_path, "rb") as f:
        raw_data = bytearray(f.read())

    # Flip a bit in the ciphertext (not the auth tag at the end, somewhere in
    # the middle)
    raw_data[5] ^= 0x01

    with open(file_path, "wb") as f:
        f.write(raw_data)

    # Attempt to download should fail integrity check
    center_token = get_token("bob_crypto@test.com", "CENTER_SUPERINTENDENT")
    response = client.get(
        f"/exams/papers/{paper.id}/download", headers={"Authorization": f"Bearer {center_token}"})

    # Restore the original file so subsequent tests don't fail unexpectedly
    raw_data[5] ^= 0x01
    with open(file_path, "wb") as f:
        f.write(raw_data)

    assert response.status_code == 500
    assert "Integrity check failed" in response.json()["detail"]


def test_cryptographic_tampering_modified_auth_tag():
    db = TestingSessionLocal()
    paper = db.query(Paper).filter(Paper.title == "Secure Exam Paper").first()
    db.close()

    file_path = os.path.join(STORAGE_DIR, paper.storage_object_id)
    with open(file_path, "rb") as f:
        raw_data = bytearray(f.read())

    # The auth tag in AES-GCM is the last 16 bytes. Flip a bit in the tag.
    raw_data[-1] ^= 0x01

    with open(file_path, "wb") as f:
        f.write(raw_data)

    # Attempt to download should fail integrity check
    center_token = get_token("bob_crypto@test.com", "CENTER_SUPERINTENDENT")
    response = client.get(
        f"/exams/papers/{paper.id}/download", headers={"Authorization": f"Bearer {center_token}"})

    # Restore the original file
    raw_data[-1] ^= 0x01
    with open(file_path, "wb") as f:
        f.write(raw_data)

    assert response.status_code == 500
    assert "Integrity check failed" in response.json()["detail"]


def test_cryptographic_wrong_key_failure():
    # Attempt to decrypt the valid ciphertext using a wrong key
    db = TestingSessionLocal()
    paper = db.query(Paper).filter(Paper.title == "Secure Exam Paper").first()
    db.close()

    file_path = os.path.join(STORAGE_DIR, paper.storage_object_id)
    with open(file_path, "rb") as f:
        raw_data = f.read()

    meta = json.loads(paper.encryption_metadata)
    document_nonce = bytes.fromhex(meta["document_nonce_b64"])

    wrong_dek = generate_key()

    with pytest.raises(ValueError):
        decrypt_document(raw_data, wrong_dek, document_nonce)
