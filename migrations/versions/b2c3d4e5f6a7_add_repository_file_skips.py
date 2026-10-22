"""add repository_file_skips table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-22 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_file_skips",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_repository_file_skips_repository_id"),
        "repository_file_skips",
        ["repository_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_repository_file_skips_repository_id"),
        table_name="repository_file_skips",
    )
    op.drop_table("repository_file_skips")
