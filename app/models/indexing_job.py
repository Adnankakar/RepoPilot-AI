import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IndexingJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


VALID_STATUSES = tuple(status.value for status in IndexingJobStatus)


def utc_now():
    return datetime.now(timezone.utc)


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'failed', 'completed')",
            name="ck_indexing_jobs_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), default="queued", index=True, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    failed_stage: Mapped[str | None] = mapped_column(
        String(60), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
