from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Identity, Index, Integer, String, Table, false, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint("role IN ('USER', 'ADMIN')", name='ck_users_role'),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Les anciens comptes n'avaient qu'un nom : le nom de famille reste inconnu.
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default='USER', server_default='USER')
    is_blacklisted: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name='ck_users_blacklisted'),
        nullable=False, default=False, server_default=false(),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name='ck_users_active'),
        nullable=False, default=True, server_default=true(),
    )


book_authors = Table(
    'book_authors', Base.metadata,
    Column('book_id', ForeignKey('books.id'), primary_key=True),
    Column('author_id', ForeignKey('authors.id'), primary_key=True, index=True),
)


class Author(Base):
    __tablename__ = 'authors'

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Book(Base):
    __tablename__ = 'books'

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    isbn: Mapped[str | None] = mapped_column(String(13), nullable=True, unique=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    genre: Mapped[str] = mapped_column(String(100), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(150), nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name='ck_books_active'),
        nullable=False, default=True, server_default=true(),
    )
    authors: Mapped[list[Author]] = relationship(secondary=book_authors, order_by=Author.id)


class BookCopy(Base):
    __tablename__ = 'book_copies'
    __table_args__ = (CheckConstraint(
        "service_status IN ('IN_SERVICE', 'DAMAGED', 'LOST', 'WITHDRAWN')",
        name='ck_book_copies_status',
    ),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id'), nullable=False, index=True)
    inventory_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    service_status: Mapped[str] = mapped_column(
        String(15), nullable=False, default='IN_SERVICE', server_default='IN_SERVICE',
    )
    book: Mapped[Book] = relationship()


class Loan(Base):
    __tablename__ = 'loans'

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    copy_id: Mapped[int] = mapped_column(ForeignKey('book_copies.id'), nullable=False, index=True)
    borrowed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(String(10), nullable=True)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    copy: Mapped[BookCopy] = relationship()

    __table_args__ = (
        CheckConstraint(
            '(closed_at IS NULL AND closure_reason IS NULL AND closed_by_id IS NULL) OR '
            '(closed_at IS NOT NULL AND closure_reason IS NOT NULL AND closed_by_id IS NOT NULL '
            "AND closure_reason IN ('RETURNED', 'LOST') AND closed_at >= borrowed_at)",
            name='ck_loans_closure',
        ),
        Index('ix_loans_user_borrowed', user_id, borrowed_at),
        # Les emprunts clôturés donnent NULL : seule la copie prêtée doit être unique.
        Index('uq_loans_active_copy', text('CASE WHEN closed_at IS NULL THEN copy_id END'), unique=True),
    )
