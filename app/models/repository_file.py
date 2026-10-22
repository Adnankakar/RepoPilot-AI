from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class RepositoryFile(Base):
    __tablename__ = "repository_files"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Relative path from the repository root, e.g. "src/main.py"
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Git blob hash (SHA-1 or SHA-256) or content-derived hash; populated
    # after git metadata extraction, null until then.
    blob_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Detected or inferred programming language, e.g. "Python"; null if unknown.
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Size in bytes
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # The commit SHA at which this file was discovered; null until populated.
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # File extension including the dot, e.g. ".py", or empty string for none
    extension: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # Detected text encoding, e.g. "utf-8"
    encoding: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
