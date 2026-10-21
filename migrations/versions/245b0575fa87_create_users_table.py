
"""create users table"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

revision: str = "245b0575fa87"
down_revision: Union[str, Sequence[str], None] = "c76300dfe5f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Create the enum type only if it doesn't already exist
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
                CREATE TYPE user_role AS ENUM ('developer', 'administrator');
            END IF;
        END$$;
    """))

    # Create the users table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID NOT NULL,
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role user_role NOT NULL DEFAULT 'developer',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            UNIQUE (email)
        );
    """))

    # Create index on email
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_users_email;"))
    conn.execute(text("DROP TABLE IF EXISTS users;"))
    conn.execute(text("DROP TYPE IF EXISTS user_role;"))
