"""Add cancellation reason to retention requests."""
from alembic import op
import sqlalchemy as sa

revision = "20260928_0002"
down_revision = "20260928_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "reason" not in {column["name"] for column in inspector.get_columns("retention_requests")}:
        op.add_column("retention_requests", sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("retention_requests", "reason")
