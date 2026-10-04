from sqlalchemy import Boolean, CheckConstraint, Identity, Integer, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

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
