"""Ensure the audit dataset-version foreign key exists on SQLite databases."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_enforce_audit_dataset_fk"
down_revision = "0002_audit_dataset_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("audit_events")}
    foreign_keys = inspector.get_foreign_keys("audit_events")
    has_dataset_fk = any(item.get("referred_table") == "dataset_versions" and
                         item.get("constrained_columns") == ["dataset_version_id"]
                         for item in foreign_keys)
    if "dataset_version_id" not in columns or not has_dataset_fk:
        with op.batch_alter_table("audit_events") as batch:
            if "dataset_version_id" not in columns:
                batch.add_column(sa.Column("dataset_version_id", sa.String(), nullable=True))
            if not has_dataset_fk:
                batch.create_foreign_key("fk_audit_events_dataset_version", "dataset_versions",
                                         ["dataset_version_id"], ["id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    foreign_keys = inspector.get_foreign_keys("audit_events")
    has_dataset_fk = any(item.get("referred_table") == "dataset_versions" and
                         item.get("constrained_columns") == ["dataset_version_id"]
                         for item in foreign_keys)
    columns = {column["name"] for column in inspector.get_columns("audit_events")}
    if "dataset_version_id" in columns:
        with op.batch_alter_table("audit_events") as batch:
            if has_dataset_fk:
                name = next(item["name"] for item in foreign_keys
                            if item.get("referred_table") == "dataset_versions" and
                            item.get("constrained_columns") == ["dataset_version_id"])
                batch.drop_constraint(name, type_="foreignkey")
            batch.drop_column("dataset_version_id")
