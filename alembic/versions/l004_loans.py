"""Emprunts et contrainte d'un seul emprunt actif par exemplaire."""

from alembic import op
import sqlalchemy as sa

revision = 'l004_loans'
down_revision = 'c003_catalogue'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'loans',
        sa.Column('id', sa.Integer(), sa.Identity(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('copy_id', sa.Integer(), nullable=False),
        sa.Column('borrowed_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('closure_reason', sa.String(10), nullable=True),
        sa.Column('closed_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['copy_id'], ['book_copies.id']),
        sa.ForeignKeyConstraint(['closed_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            '(closed_at IS NULL AND closure_reason IS NULL AND closed_by_id IS NULL) OR '
            '(closed_at IS NOT NULL AND closure_reason IS NOT NULL AND closed_by_id IS NOT NULL '
            "AND closure_reason IN ('RETURNED', 'LOST') AND closed_at >= borrowed_at)",
            name='ck_loans_closure',
        ),
    )
    op.create_index('ix_loans_copy_id', 'loans', ['copy_id'])
    op.create_index('ix_loans_closed_by_id', 'loans', ['closed_by_id'])
    op.create_index('ix_loans_user_borrowed', 'loans', ['user_id', 'borrowed_at'])
    op.create_index('uq_loans_active_copy', 'loans', [
        sa.text('CASE WHEN closed_at IS NULL THEN copy_id END'),
    ], unique=True)


def downgrade():
    op.drop_index('uq_loans_active_copy', table_name='loans')
    op.drop_index('ix_loans_user_borrowed', table_name='loans')
    op.drop_index('ix_loans_closed_by_id', table_name='loans')
    op.drop_index('ix_loans_copy_id', table_name='loans')
    op.drop_table('loans')
