"""Persist workflow state and distinguish proactive retention from cancellation."""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0003"
down_revision = "20260928_0002"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("retention_requests")}
    if "request_kind" not in columns:
        op.add_column("retention_requests", sa.Column("request_kind", sa.String(20), nullable=False, server_default="cancellation"))
    if "workflow_state" not in columns:
        op.add_column("retention_requests", sa.Column("workflow_state", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("retention_requests", "workflow_state")
    op.drop_column("retention_requests", "request_kind")
