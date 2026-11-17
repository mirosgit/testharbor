"""case external id

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17 20:50:14.538976
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('test_cases', sa.Column('external_id', sa.String(length=200), nullable=True))
    op.create_index('ix_test_cases_suite_external_id', 'test_cases', ['suite_id', 'external_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_test_cases_suite_external_id', table_name='test_cases')
    op.drop_column('test_cases', 'external_id')
