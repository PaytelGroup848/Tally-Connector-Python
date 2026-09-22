"""create sync_queue table

Revision ID: 001_sync_queue
Revises: None
Create Date: 2026-08-27

"""
from alembic import op
import sqlalchemy as sa

revision = "001_sync_queue"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "sync_queue",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("payload_type", sa.String(length=50), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sync_queue_payload_type", "sync_queue", ["payload_type"])
    op.create_index("idx_sync_queue_status", "sync_queue", ["status"])
    op.create_index("idx_sync_queue_status_created", "sync_queue", ["status", "created_at"])

def downgrade() -> None:
    op.drop_index("idx_sync_queue_status_created", table_name="sync_queue")
    op.drop_index("idx_sync_queue_status", table_name="sync_queue")
    op.drop_index("idx_sync_queue_payload_type", table_name="sync_queue")
    op.drop_table("sync_queue")
