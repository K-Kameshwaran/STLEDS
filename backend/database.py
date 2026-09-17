"""
File Overview:
This file establishes the connection to the database using SQLAlchemy.
For Day 2, we default to SQLite for local development but use the environment
variable `DATABASE_URL` so it can be seamlessly switched to Postgres.

Important Classes/Functions:
- `engine`: The SQLAlchemy engine instance managing connections.
- `SessionLocal`: A factory for creating database sessions.
- `Base`: The declarative base class that all models inherit from.
- `get_db()`: A dependency function for FastAPI to yield a database session per request.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# We use SQLite by default if DATABASE_URL is not set or if we force local dev
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stleds.db")

# SQLite requires check_same_thread=False since FastAPI handles concurrency
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """
    Dependency function to provide a database session for a single request.
    
    Why it's required:
    It ensures that each API request gets its own database connection session,
    which is safely closed after the request is processed, preventing memory leaks
    or connection pool exhaustion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
