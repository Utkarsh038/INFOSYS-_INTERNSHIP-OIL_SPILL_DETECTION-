import os
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (create_engine, Column, Integer, String, Float, LargeBinary, DateTime, ForeignKey)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError

from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in environment (.env)")

# Many hosted Postgres databases require SSL and will close plain TCP connections.
# Configure the engine to use SSL for non-local databases and enable pool_pre_ping
# so SQLAlchemy checks connections before using them (avoids "SSL connection has been
# closed unexpectedly" when the server has closed an idle connection).
connect_args = {}
lower_db = DATABASE_URL.lower()
# If the URL points to localhost, avoid forcing SSL. Otherwise request SSL.
if not ("localhost" in lower_db or "127.0.0.1" in lower_db or lower_db.startswith("postgresql+psycopg2://localhost") ):
    connect_args = {"sslmode": "require"}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
    # tune the pool for lightweight apps; adjust if you see pool timeouts
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Prefer Argon2 for hashing to avoid bcrypt's 72-byte limit and for stronger security.
# Requires `argon2-cffi` to be installed.
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)

    analyses = relationship("Analysis", back_populates="user")


class Analysis(Base):
    __tablename__ = "analyses"
    analysis_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    spill_percentage = Column(Float, nullable=False)
    original_image_blob = Column(LargeBinary, nullable=False)
    overlay_image_blob = Column(LargeBinary, nullable=False)
    original_filename = Column(String, nullable=True)

    user = relationship("User", back_populates="analyses")


def init_db():
    Base.metadata.create_all(bind=engine)


def create_user(username: str, password: str) -> Optional[int]:
    session = SessionLocal()
    try:
        user = User(username=username, password_hash=pwd_context.hash(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.user_id
    except IntegrityError:
        session.rollback()
        return None
    finally:
        session.close()


def verify_user(username: str, password: str) -> Optional[int]:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            return None
        if pwd_context.verify(password, user.password_hash):
            return user.user_id
        return None
    finally:
        session.close()


def save_analysis(user_id: int, spill_percentage: float, original_bytes: bytes, overlay_bytes: bytes, filename: Optional[str] = None) -> int:
    session = SessionLocal()
    try:
        analysis = Analysis(user_id=user_id, timestamp=datetime.utcnow(), spill_percentage=spill_percentage,
                            original_image_blob=original_bytes, overlay_image_blob=overlay_bytes, original_filename=filename)
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
        return analysis.analysis_id
    finally:
        session.close()


def delete_analysis(analysis_id: int) -> bool:
    session = SessionLocal()
    try:
        row = session.query(Analysis).filter(Analysis.analysis_id == analysis_id).first()
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True
    finally:
        session.close()


def get_analyses_for_user(user_id: int) -> List[dict]:
    session = SessionLocal()
    try:
        rows = session.query(Analysis).filter(Analysis.user_id == user_id).order_by(Analysis.timestamp.desc()).all()
        results = []
        for r in rows:
            results.append({
                "analysis_id": r.analysis_id,
                "timestamp": r.timestamp,
                "spill_percentage": r.spill_percentage,
                "original_image_blob": r.original_image_blob,
                "overlay_image_blob": r.overlay_image_blob,
                "original_filename": r.original_filename,
            })
        return results
    finally:
        session.close()
