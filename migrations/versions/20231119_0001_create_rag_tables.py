"""Alembic migration to create RAG storage tables.

Revision ID: 20231119_0001
Revises: None
Create Date: 2026-11-19 12:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20231119_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension if using PostgreSQL
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Repository table (optional, for grouping chunks)
    op.create_table(
        "repository",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("url", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # File metadata table – one row per source file
    op.create_table(
        "file_metadata",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repository.id"), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "file_path", name="uq_file_repo_path"),
    )

    # Chunks table – stores raw code chunks and vector embeddings
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repository.id"), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("symbol", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", postgresql.VECTOR, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_chunks_repo_file", "repository_id", "file_path"),
        sa.Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw"),
    )

    # Optional separate embeddings table (if the app prefers split storage)
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repository.id"), nullable=False),
        sa.Column("chunk_id", sa.Integer, sa.ForeignKey("chunks.id"), nullable=False),
        sa.Column("embedding", postgresql.VECTOR, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("chunk_id", name="uq_embeddings_chunk"),
    )


def downgrade() -> None:
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("file_metadata")
    op.drop_table("repository")
    # Note: the pgvector extension is left in place – safe to keep.
