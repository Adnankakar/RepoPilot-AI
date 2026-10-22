from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Repository(Base):
    __tablename__ = "repositories"

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "provider",
            "external_id",
            name="uq_repository_owner_provider_external",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    owner_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="github", nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    indexed_commit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )