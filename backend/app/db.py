from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, LargeBinary, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .websocket_manager import ws_manager

DATA_DIR = Path(__file__).resolve().parent.parent / ".data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "settlex.db"
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="Settlex User")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    credentials: Mapped[list["WebAuthnCredential"]] = relationship(back_populates="user")
    sessions: Mapped[list["NegotiationSession"]] = relationship(back_populates="user")


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)  # base64url credential id
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    device_type: Mapped[str] = mapped_column(String(40), default="platform")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="credentials")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NegotiationSession(Base):
    __tablename__ = "negotiation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    negotiation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    supplier: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(40), default="paid")
    tx_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    explorer_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[Optional[User]] = relationship(back_populates="sessions")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def explorer_url_for(tx_hash: Optional[str]) -> Optional[str]:
    if not tx_hash:
        return None
    network = os.environ.get("STELLAR_NETWORK", "TESTNET").upper()
    slug = "public" if network in {"PUBLIC", "MAINNET"} else "testnet"
    return f"https://stellar.expert/explorer/{slug}/tx/{tx_hash}"


def persist_settlement(
    *,
    negotiation_id: Optional[str],
    supplier: str,
    amount: float,
    tx_hash: Optional[str],
    status: str,
    user_id: Optional[str] = None,
) -> NegotiationSession:
    url = explorer_url_for(tx_hash)
    with session_scope() as db:
        row = NegotiationSession(
            user_id=user_id,
            negotiation_id=negotiation_id,
            supplier=supplier or "",
            amount=float(amount or 0),
            status=status,
            tx_hash=tx_hash,
            explorer_url=url,
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        snapshot = NegotiationSession(
            id=row.id,
            user_id=row.user_id,
            negotiation_id=row.negotiation_id,
            supplier=row.supplier,
            amount=row.amount,
            status=row.status,
            tx_hash=row.tx_hash,
            explorer_url=row.explorer_url,
            created_at=row.created_at,
        )
    return snapshot


async def announce_settlement(
    *,
    negotiation_id: Optional[str],
    supplier: str,
    amount: float,
    tx_hash: Optional[str],
    status: str,
    user_id: Optional[str] = None,
) -> dict:
    try:
        row = persist_settlement(
            negotiation_id=negotiation_id,
            supplier=supplier,
            amount=amount,
            tx_hash=tx_hash,
            status=status,
            user_id=user_id,
        )
    except Exception as exc:
        print(f"SQLite persist failed (non-fatal): {exc}")
        row = None
        url = explorer_url_for(tx_hash)
    else:
        url = row.explorer_url

    payload = {
        "type": "settlement",
        "negotiation_id": negotiation_id,
        "supplier": supplier,
        "amount": amount,
        "tx_hash": tx_hash,
        "status": status,
        "explorer_url": url,
        "session_id": getattr(row, "id", None),
    }
    await ws_manager.broadcast(payload)
    if tx_hash:
        await ws_manager.broadcast(
            {
                "type": "anchor_step",
                "message": f"View Settlement on Stellar Expert: {url}",
                "level": "info",
            }
        )
    return payload
