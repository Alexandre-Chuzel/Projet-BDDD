"""Catalogue : auteurs, livres, association des auteurs et exemplaires."""

from alembic import op
import sqlalchemy as sa

revision = 'c003_catalogue'
down_revision = 'u002_user_management'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'authors',
        sa.Column('id', sa.Integer(), sa.Identity(), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'books',
        sa.Column('id', sa.Integer(), sa.Identity(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('isbn', sa.String(13), nullable=True),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('genre', sa.String(100), nullable=False),
        sa.Column('publisher', sa.String(150), nullable=True),
        sa.Column('publication_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint('is_active IN (0, 1)', name='ck_books_active'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('isbn'),
    )
    op.create_table(
        'book_authors',
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id']),
        sa.ForeignKeyConstraint(['author_id'], ['authors.id']),
        sa.PrimaryKeyConstraint('book_id', 'author_id'),
    )
    op.create_index('ix_book_authors_author_id', 'book_authors', ['author_id'])
    op.create_table(
        'book_copies',
        sa.Column('id', sa.Integer(), sa.Identity(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('inventory_code', sa.String(50), nullable=False),
        sa.Column('service_status', sa.String(15), nullable=False, server_default='IN_SERVICE'),
        sa.CheckConstraint("service_status IN ('IN_SERVICE', 'DAMAGED', 'LOST', 'WITHDRAWN')", name='ck_book_copies_status'),
        sa.ForeignKeyConstraint(['book_id'], ['books.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inventory_code'),
    )
    op.create_index('ix_book_copies_book_id', 'book_copies', ['book_id'])


def downgrade():
    op.drop_index('ix_book_copies_book_id', table_name='book_copies')
    op.drop_table('book_copies')
    op.drop_index('ix_book_authors_author_id', table_name='book_authors')
    op.drop_table('book_authors')
    op.drop_table('books')
    op.drop_table('authors')
