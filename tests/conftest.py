import pytest
import os
from dotenv import load_dotenv

# Ensure local test environment uses the .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"), override=True)
os.environ["ENVIRONMENT"] = "development"
os.environ.pop("KMS_ENDPOINT", None)
os.environ.pop("R2_ENDPOINT", None)

from backend.limiter import limiter

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Clears the in-memory rate limiter storage before every test 
    so that tests don't share rate limits and fail with 429 Too Many Requests.
    """
    limiter._storage.reset()
