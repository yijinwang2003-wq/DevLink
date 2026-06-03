"""add user is_superuser

Revision ID: 20260603_0005
Revises: 20260603_0004
Create Date: 2026-06-03 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "20260603_0005"
down_revision = "20260603_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.alter_column("users", "is_superuser", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_superuser")
