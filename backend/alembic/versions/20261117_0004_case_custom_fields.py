"""case custom fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17 21:09:16.941185
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('test_cases', sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.create_index('ix_test_cases_custom_fields', 'test_cases', ['custom_fields'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('ix_test_cases_custom_fields', table_name='test_cases', postgresql_using='gin')
    op.drop_column('test_cases', 'custom_fields')
