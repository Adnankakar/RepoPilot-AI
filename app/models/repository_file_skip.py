from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class RepositoryFileSkip(Base):
    __tablename__ = "repository_file_skips"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Relative path from the repository root, e.g. "node_modules/lodash/index.js"
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Human-readable reason this file was skipped, e.g. "dependency directory"
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    skipped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
