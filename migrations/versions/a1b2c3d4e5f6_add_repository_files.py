"""add repository_files table

Revision ID: a1b2c3d4e5f6
Revises: 0de59cda42a2
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "0de59cda42a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("blob_hash", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("extension", sa.String(length=50), nullable=False),
        sa.Column("encoding", sa.String(length=30), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_repository_files_repository_id"),
        "repository_files",
        ["repository_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_repository_files_repository_id"),
        table_name="repository_files",
    )
    op.drop_table("repository_files")
