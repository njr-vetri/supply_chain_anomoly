"""Create Phase 8 relational records."""
from alembic import op

from src.core.repository import Base

revision = "0001_phase8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
