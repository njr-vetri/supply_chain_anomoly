"""Add company ownership, soft deletion, and onboarding entities."""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from src.core.repository import Base

revision = "0004_company_tenancy"
down_revision = "0003_enforce_audit_dataset_fk"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "workspaces", "projects", "data_sources", "mapping_versions", "import_jobs", "dataset_versions",
    "model_versions", "predictions", "anomalies", "incidents", "evidence", "hypotheses",
    "recommendations", "approvals", "actions", "outcomes", "audit_events", "quality_snapshots",
)


def upgrade() -> None:
    bind = op.get_bind()
    # Creates Company and new onboarding tables, while leaving existing tables unchanged.
    Base.metadata.create_all(bind=bind)
    company_table = sa.Table("companies", sa.MetaData(), autoload_with=bind)
    if bind.execute(sa.select(company_table.c.id).where(company_table.c.id == "local")).first() is None:
        bind.execute(company_table.insert().values(id="local", company_id="local", name="Local workspace",
                                                    created_at=datetime.now(timezone.utc)))
    for table_name in TENANT_TABLES:
        columns = {column["name"] for column in inspect(bind).get_columns(table_name)}
        if "company_id" not in columns:
            with op.batch_alter_table(table_name) as batch:
                batch.add_column(sa.Column("company_id", sa.String(), nullable=True))
        if "deleted_at" not in columns:
            with op.batch_alter_table(table_name) as batch:
                batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        bind.execute(sa.text(f"UPDATE {table_name} SET company_id = 'local' WHERE company_id IS NULL"))
        inspector = inspect(bind)
        foreign_keys = inspector.get_foreign_keys(table_name)
        has_company_fk = any(item.get("referred_table") == "companies" and
                             item.get("constrained_columns") == ["company_id"] for item in foreign_keys)
        if not has_company_fk:
            with op.batch_alter_table(table_name) as batch:
                batch.alter_column("company_id", existing_type=sa.String(), nullable=False)
                batch.create_foreign_key(f"fk_{table_name}_company", "companies", ["company_id"], ["id"])


def downgrade() -> None:
    # Downgrade intentionally retains tenant columns and audit history.
    pass
