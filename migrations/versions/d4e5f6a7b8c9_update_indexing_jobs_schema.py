"""update indexing_jobs schema

Revision ID: d4e5f6a7b8c9
Revises: c3c3ed35500e
Create Date: 2026-11-11 10:00:00.000000

Adds: attempt_count, started_at, finished_at, error_summary, failed_stage.
Renames the default status value from 'pending' / 'cloned' etc. to the new
valid set: queued | running | failed | completed.
Adds a CHECK constraint enforcing the allowed status values.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3c3ed35500e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Migrate legacy status values to the new vocabulary BEFORE adding
    #    the CHECK constraint so existing rows don't violate it.
    op.execute(
        """
        UPDATE indexing_jobs
        SET status = CASE
            WHEN status IN ('cloned', 'partial') THEN 'completed'
            WHEN status IN ('clone_failed', 'ingestion_failed') THEN 'failed'
            WHEN status = 'running' THEN 'running'
            ELSE 'queued'
        END
        """
    )

    # 2. Add new columns.
    op.add_column(
        "indexing_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "indexing_jobs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "indexing_jobs",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "indexing_jobs",
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "indexing_jobs",
        sa.Column("failed_stage", sa.String(length=60), nullable=True),
    )

    # 3. Add CHECK constraint.
    op.create_check_constraint(
        "ck_indexing_jobs_status",
        "indexing_jobs",
        "status IN ('queued', 'running', 'failed', 'completed')",
    )

    # 4. Add index on status.
    op.create_index(
        op.f("ix_indexing_jobs_status"),
        "indexing_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_indexing_jobs_status"), table_name="indexing_jobs")
    op.drop_constraint("ck_indexing_jobs_status", "indexing_jobs", type_="check")
    op.drop_column("indexing_jobs", "failed_stage")
    op.drop_column("indexing_jobs", "error_summary")
    op.drop_column("indexing_jobs", "finished_at")
    op.drop_column("indexing_jobs", "started_at")
    op.drop_column("indexing_jobs", "attempt_count")
