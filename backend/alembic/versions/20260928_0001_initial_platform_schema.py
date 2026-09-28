"""Initial normalized hotel platform schema.

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260928_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    from backend.app.database.base import Base
    import backend.app.models  # noqa: F401
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from backend.app.database.base import Base
    import backend.app.models  # noqa: F401
    Base.metadata.drop_all(bind=bind)
