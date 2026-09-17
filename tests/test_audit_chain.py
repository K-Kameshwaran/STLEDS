import pytest
from datetime import datetime, timezone
import hashlib
import json


from backend.audit.models import AuditLog
from backend.audit.service import create_audit_record, verify_audit_chain, GENESIS_HASH

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_audit_chain.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_audit_chain_creation_and_verification():
    """
    Test that audit records form a valid mathematical chain and are verifiable.
    """
    db = TestingSessionLocal()

    # 1. Clear any existing audit logs from previous tests
    db.query(AuditLog).delete()
    db.commit()

    # 2. Create multiple audit records
    create_audit_record(
        db,
        action="LOGIN_SUCCESS",
        result="SUCCESS",
        actor_id=1)
    create_audit_record(
        db,
        action="UPLOAD",
        result="SUCCESS",
        actor_id=1,
        exam_id=1,
        resource_id=1)
    create_audit_record(
        db,
        action="RELEASE_AUTHORIZED",
        result="SUCCESS",
        actor_id=2,
        exam_id=1)

    # 3. Verify the chain successfully
    result = verify_audit_chain(db)
    assert result["valid"] is True
    assert result["first_invalid_record"] is None

    # 4. Intentionally modify a historical audit record (Tamper)
    second_record = db.query(AuditLog).order_by(AuditLog.id).offset(1).first()
    assert second_record is not None

    # Malicious actor changes the action
    second_record.action = "TAMPERED_ACTION"
    db.commit()

    # 5. Confirm verification fails and identifies the tampered record
    tampered_result = verify_audit_chain(db)
    assert tampered_result["valid"] is False
    assert tampered_result["first_invalid_record"] == second_record.id

    db.close()
