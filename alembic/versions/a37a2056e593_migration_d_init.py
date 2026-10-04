"""Migration d'init

Revision ID: a37a2056e593
Revises: b001_initial_users
Create Date: 2026-09-17 14:37:34.259445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a37a2056e593'
down_revision: Union[str, Sequence[str], None] = 'b001_initial_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Oracle conserve un ALTER TABLE ; SQLite utilise une copie de table.
    with op.batch_alter_table('users') as batch:
        batch.alter_column('password', existing_type=sa.VARCHAR(length=255), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users') as batch:
        batch.alter_column('password', existing_type=sa.VARCHAR(length=255), nullable=True)
