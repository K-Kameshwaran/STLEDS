"""
File Overview:
This file is the main entry point for the FastAPI backend application.
It initializes the FastAPI app instance and defines the foundational routes,
such as the `/health` endpoint required for Day 1 validation.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import os

from backend.limiter import limiter

# Initialize the FastAPI application
app = FastAPI(title="stleds Backend", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS securely using environment variable or safe default
# Day 8: Do not use unrestricted wildcard origins in production
allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.auth.router import router as auth_router
from backend.exams.router import router as exams_router
from backend.release.router import router as release_router
from backend.audit.router import router as audit_router

app.include_router(auth_router)
app.include_router(exams_router)
app.include_router(release_router)
app.include_router(audit_router)

@app.get("/health")
def health_check():
    """
    Health check endpoint to verify that the backend is running.
    Expected response: {"status": "ok"}
    """
    return {"status": "ok"}

"""
The health_check function responds to GET requests on the `/health` path.
This is a simple way to verify that the application has started successfully and is ready to accept requests.
It is standard practice for cloud deployments to use such endpoints for health monitoring.
"""
