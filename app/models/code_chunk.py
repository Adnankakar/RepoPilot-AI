from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    __table_args__ = (
        UniqueConstraint(
            "file_id",
            "chunk_index",
            name="uq_code_chunks_file_chunk_index",
        ),
        Index(
            "ix_code_chunks_repository_file_path",
            "repository_id",
            "file_path",
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
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repository_files.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    @property
    def path(self) -> str:
        return self.file_path
