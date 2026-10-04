"""Identité, rôles, liste noire et suppression logique des utilisateurs."""

from alembic import op
import sqlalchemy as sa

revision = 'u002_user_management'
down_revision = 'a37a2056e593'
branch_labels = None
depends_on = None


def upgrade():
    # Renommer conserve les noms et les mots de passe hachés existants.
    with op.batch_alter_table('users') as batch:
        batch.alter_column('name', new_column_name='first_name', existing_type=sa.String(100))
        batch.alter_column('password', new_column_name='password_hash', existing_type=sa.String(255))
        batch.add_column(sa.Column('last_name', sa.String(100), nullable=True))
        batch.add_column(sa.Column('phone', sa.String(30), nullable=True))
        batch.add_column(sa.Column('role', sa.String(10), nullable=False, server_default='USER'))
        batch.add_column(sa.Column('is_blacklisted', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.create_check_constraint('ck_users_role', "role IN ('USER', 'ADMIN')")
        batch.create_check_constraint('ck_users_blacklisted', 'is_blacklisted IN (0, 1)')
        batch.create_check_constraint('ck_users_active', 'is_active IN (0, 1)')


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('ck_users_role', type_='check')
        batch.drop_constraint('ck_users_blacklisted', type_='check')
        batch.drop_constraint('ck_users_active', type_='check')
        batch.drop_column('is_active')
        batch.drop_column('is_blacklisted')
        batch.drop_column('role')
        batch.drop_column('phone')
        batch.drop_column('last_name')
        batch.alter_column('first_name', new_column_name='name', existing_type=sa.String(100))
        batch.alter_column('password_hash', new_column_name='password', existing_type=sa.String(255))
