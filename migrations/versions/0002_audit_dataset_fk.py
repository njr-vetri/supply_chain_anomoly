"""Link audit events to their dataset version when known."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_audit_dataset_fk"
down_revision = "0001_phase8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("audit_events")}
    if "dataset_version_id" not in columns:
        with op.batch_alter_table("audit_events") as batch:
            batch.add_column(sa.Column("dataset_version_id", sa.String(), nullable=True))
            batch.create_foreign_key("fk_audit_events_dataset_version", "dataset_versions",
                                     ["dataset_version_id"], ["id"])


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("audit_events")}
    if "dataset_version_id" in columns:
        with op.batch_alter_table("audit_events") as batch:
            batch.drop_constraint("fk_audit_events_dataset_version", type_="foreignkey")
            batch.drop_column("dataset_version_id")
