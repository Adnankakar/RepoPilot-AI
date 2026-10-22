"""update repository_files to new schema

Renames relative_path -> path, adds blob_hash, language, commit_sha,
encoding columns to match the current RepositoryFile model.

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-10-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename relative_path -> path
    op.alter_column(
        "repository_files",
        "relative_path",
        new_column_name="path",
        existing_type=sa.String(length=2048),
        existing_nullable=False,
    )

    # Add new columns
    op.add_column(
        "repository_files",
        sa.Column("blob_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "repository_files",
        sa.Column("language", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "repository_files",
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "repository_files",
        sa.Column(
            "encoding",
            sa.String(length=30),
            nullable=False,
            server_default="",
        ),
    )
    # Remove server default after adding so new rows must supply a value
    op.alter_column("repository_files", "encoding", server_default=None)


def downgrade() -> None:
    op.drop_column("repository_files", "encoding")
    op.drop_column("repository_files", "commit_sha")
    op.drop_column("repository_files", "language")
    op.drop_column("repository_files", "blob_hash")
    op.alter_column(
        "repository_files",
        "path",
        new_column_name="relative_path",
        existing_type=sa.String(length=2048),
        existing_nullable=False,
    )
