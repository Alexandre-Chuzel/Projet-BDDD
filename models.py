from sqlalchemy import Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True
    )
    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )