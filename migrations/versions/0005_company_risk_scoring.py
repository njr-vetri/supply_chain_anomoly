"""Add immutable per-company risk scoring configuration history."""
from alembic import op

from src.core.repository import Base

revision = "0005_company_risk_scoring"
down_revision = "0004_company_tenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Uses the same SQLAlchemy metadata as the repository for backend portability.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Keep historical risk configurations available for audit.
    pass
