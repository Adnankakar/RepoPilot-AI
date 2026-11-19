"""Database models and utilities for conversation and evidence tracking.

This module defines three core tables:

* **Conversation** – represents a user‑assistant interaction session.
* **Message** – a single user or assistant turn; stores the raw text and the
  model metadata (model name, temperature, token usage, etc.) as JSON.
* **EvidenceReference** – links a Message to the retrieved chunks that were
  used to answer the question. It stores the chunk identifier, a relevance
  score, and optional citation metadata.

Utility functions are provided to create a conversation, add messages, record
evidence, and query recent questions or the full indexing history for a
conversation.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings

# ---------------------------------------------------------------------------
# SQLAlchemy base and engine
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass

# The ``DATABASE_URL`` from .env already points at a PostgreSQL instance.
# We use a simple synchronous engine for the purpose of this example.
engine = create_engine(settings.database_url, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Relationship to messages
    messages: Mapped[List["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Conversation id={self.id} started_at={self.started_at}>"


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    model_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    evidence: Mapped[List["EvidenceReference"]] = relationship(back_populates="message", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Message id={self.id} role={self.role}>"


class EvidenceReference(Base):
    __tablename__ = "evidence_reference"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    citation_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    message: Mapped[Message] = relationship(back_populates="evidence")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvidenceReference id={self.id} chunk_id={self.chunk_id}>"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create tables if they do not exist.
    Call once at application start‑up.
    """
    Base.metadata.create_all(engine)


def start_conversation() -> Conversation:
    """Create a new conversation row and return the ORM object."""
    with SessionLocal() as session:
        conv = Conversation()
        session.add(conv)
        session.commit()
        session.refresh(conv)
        return conv


def add_message(
    conversation_id: int,
    role: str,
    content: str,
    model_metadata: Optional[dict] = None,
) -> Message:
    """Insert a Message and return the persisted object."""
    with SessionLocal() as session:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model_metadata=model_metadata,
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return msg


def add_evidence(
    message_id: int,
    chunk_id: str,
    relevance_score: float,
    citation_metadata: Optional[dict] = None,
) -> EvidenceReference:
    """Record a single evidence reference for a message."""
    with SessionLocal() as session:
        ev = EvidenceReference(
            message_id=message_id,
            chunk_id=chunk_id,
            relevance_score=relevance_score,
            citation_metadata=citation_metadata,
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)
        return ev


def get_recent_questions(limit: int = 10) -> List[Message]:
    """Return the most recent *user* messages (questions) across all conversations.
    """
    with SessionLocal() as session:
        stmt = (
            session.query(Message)
            .filter(Message.role == "user")
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return stmt.all()


def get_indexing_history(conversation_id: int) -> List[EvidenceReference]:
    """Return all evidence references for a given conversation, ordered by time.
    """
    with SessionLocal() as session:
        stmt = (
            session.query(EvidenceReference)
            .join(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(EvidenceReference.id.asc())
        )
        return stmt.all()

# Initialise DB on import (safe for idempotent execution)
init_db()
