"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-17 18:44:47.882881
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('prefix', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_api_tokens_token_hash'))
    )
    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_table('suites',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_suites_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suites'))
    )
    op.create_index(op.f('ix_suites_project_id'), 'suites', ['project_id'], unique=False)
    op.create_table('test_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('source', sa.Enum('manual', 'ci', name='run_source', native_enum=False, create_constraint=True, length=32), server_default='manual', nullable=False),
    sa.Column('branch', sa.String(length=300), nullable=True),
    sa.Column('commit', sa.String(length=100), nullable=True),
    sa.Column('build_url', sa.String(length=2000), nullable=True),
    sa.Column('closed', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_test_runs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_test_runs'))
    )
    op.create_index(op.f('ix_test_runs_project_id'), 'test_runs', ['project_id'], unique=False)
    op.create_table('sections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('suite_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['sections.id'], name=op.f('fk_sections_parent_id_sections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['suite_id'], ['suites.id'], name=op.f('fk_sections_suite_id_suites'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sections'))
    )
    op.create_index(op.f('ix_sections_parent_id'), 'sections', ['parent_id'], unique=False)
    op.create_index(op.f('ix_sections_suite_id'), 'sections', ['suite_id'], unique=False)
    op.create_table('test_cases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('suite_id', sa.Integer(), nullable=False),
    sa.Column('section_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('preconditions', sa.Text(), server_default='', nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('expected_result', sa.Text(), server_default='', nullable=False),
    sa.Column('priority', sa.Enum('low', 'medium', 'high', 'critical', name='priority', native_enum=False, create_constraint=True, length=32), server_default='medium', nullable=False),
    sa.Column('type', sa.Enum('functional', 'regression', 'smoke', 'acceptance', 'performance', 'security', 'other', name='case_type', native_enum=False, create_constraint=True, length=32), server_default='functional', nullable=False),
    sa.Column('tags', postgresql.ARRAY(sa.String(length=100)), server_default=sa.text("'{}'::varchar[]"), nullable=False),
    sa.Column('automation_status', sa.Enum('manual', 'automated', 'to_be_automated', name='automation_status', native_enum=False, create_constraint=True, length=32), server_default='manual', nullable=False),
    sa.Column('automation_key', sa.String(length=1000), nullable=True),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_test_cases_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], name=op.f('fk_test_cases_section_id_sections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['suite_id'], ['suites.id'], name=op.f('fk_test_cases_suite_id_suites'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_test_cases')),
    sa.UniqueConstraint('project_id', 'automation_key', name='uq_test_cases_project_automation_key')
    )
    op.create_index(op.f('ix_test_cases_project_id'), 'test_cases', ['project_id'], unique=False)
    op.create_index('ix_test_cases_section_position', 'test_cases', ['section_id', 'position'], unique=False)
    op.create_index(op.f('ix_test_cases_suite_id'), 'test_cases', ['suite_id'], unique=False)
    op.create_index('ix_test_cases_tags', 'test_cases', ['tags'], unique=False, postgresql_using='gin')
    op.create_table('run_cases',
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('passed', 'failed', 'blocked', 'skipped', 'retest', 'untested', name='result_status', native_enum=False, create_constraint=True, length=32), server_default='untested', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['test_cases.id'], name=op.f('fk_run_cases_case_id_test_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], name=op.f('fk_run_cases_run_id_test_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('run_id', 'case_id', name=op.f('pk_run_cases'))
    )
    op.create_index(op.f('ix_run_cases_case_id'), 'run_cases', ['case_id'], unique=False)
    op.create_table('test_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('passed', 'failed', 'blocked', 'skipped', 'retest', 'untested', name='result_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('stack_trace', sa.Text(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['test_cases.id'], name=op.f('fk_test_results_case_id_test_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], name=op.f('fk_test_results_run_id_test_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_test_results'))
    )
    op.create_index(op.f('ix_test_results_case_id'), 'test_results', ['case_id'], unique=False)
    op.create_index('ix_test_results_run_case', 'test_results', ['run_id', 'case_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_test_results_run_case', table_name='test_results')
    op.drop_index(op.f('ix_test_results_case_id'), table_name='test_results')
    op.drop_table('test_results')
    op.drop_index(op.f('ix_run_cases_case_id'), table_name='run_cases')
    op.drop_table('run_cases')
    op.drop_index('ix_test_cases_tags', table_name='test_cases', postgresql_using='gin')
    op.drop_index(op.f('ix_test_cases_suite_id'), table_name='test_cases')
    op.drop_index('ix_test_cases_section_position', table_name='test_cases')
    op.drop_index(op.f('ix_test_cases_project_id'), table_name='test_cases')
    op.drop_table('test_cases')
    op.drop_index(op.f('ix_sections_suite_id'), table_name='sections')
    op.drop_index(op.f('ix_sections_parent_id'), table_name='sections')
    op.drop_table('sections')
    op.drop_index(op.f('ix_test_runs_project_id'), table_name='test_runs')
    op.drop_table('test_runs')
    op.drop_index(op.f('ix_suites_project_id'), table_name='suites')
    op.drop_table('suites')
    op.drop_table('projects')
    op.drop_table('api_tokens')
