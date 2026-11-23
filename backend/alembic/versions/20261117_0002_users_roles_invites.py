"""users roles invites

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17 20:11:29.870090
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('admin', 'tester', name='role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('session_version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('failed_logins', sa.Integer(), server_default='0', nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('invites',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.Enum('invite', 'reset', name='invite_purpose', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('role', sa.Enum('admin', 'tester', name='role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_invites_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_invites_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invites')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_invites_token_hash'))
    )
    # Tokens created before user accounts existed have no owner: remove them.
    # data-loss-ok: ownerless tokens can't act as anyone once tokens act as their owner.
    op.execute("DELETE FROM api_tokens")
    op.add_column('api_tokens', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_api_tokens_user_id'), 'api_tokens', ['user_id'], unique=False)
    op.create_foreign_key(op.f('fk_api_tokens_user_id_users'), 'api_tokens', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.add_column('test_results', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_test_results_user_id_users'), 'test_results', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    op.add_column('test_runs', sa.Column('created_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_test_runs_created_by_id_users'), 'test_runs', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_test_runs_created_by_id_users'), 'test_runs', type_='foreignkey')
    op.drop_column('test_runs', 'created_by_id')
    op.drop_constraint(op.f('fk_test_results_user_id_users'), 'test_results', type_='foreignkey')
    op.drop_column('test_results', 'user_id')
    op.drop_constraint(op.f('fk_api_tokens_user_id_users'), 'api_tokens', type_='foreignkey')
    op.drop_index(op.f('ix_api_tokens_user_id'), table_name='api_tokens')
    op.drop_column('api_tokens', 'user_id')
    op.drop_table('invites')
    op.drop_table('users')
