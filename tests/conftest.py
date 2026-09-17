import pytest
from backend.limiter import limiter

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Clears the in-memory rate limiter storage before every test 
    so that tests don't share rate limits and fail with 429 Too Many Requests.
    """
    limiter._storage.reset()
