from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserIdentity(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=150)
    phone: str | None = Field(default=None, max_length=30, pattern=r'^\+?[0-9 ()-]{6,30}$')

    model_config = ConfigDict(extra='forbid')

    @field_validator('first_name', 'last_name', 'phone', mode='before')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserCreate(UserIdentity):
    password: str = Field(min_length=8, max_length=128)


class AdminUserCreate(UserCreate):
    role: Literal['USER', 'ADMIN'] = 'USER'


class UserUpdate(UserIdentity):
    # Une modification de profil ne nécessite pas de changer le mot de passe.
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Literal['USER', 'ADMIN'] | None = None


class BlacklistUpdate(BaseModel):
    is_blacklisted: bool
    model_config = ConfigDict(extra='forbid')


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    email: str
    phone: str | None
    role: Literal['USER', 'ADMIN']
    is_blacklisted: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AuthorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    model_config = ConfigDict(extra='forbid')

    @field_validator('first_name', 'last_name', mode='before')
    @classmethod
    def strip_names(cls, value):
        return value.strip() if isinstance(value, str) else value


class AuthorResponse(AuthorCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    genre: str = Field(min_length=1, max_length=100)
    author_ids: list[int] = Field(min_length=1)
    isbn: str | None = Field(default=None, max_length=13)
    description: str | None = Field(default=None, max_length=1000)
    publisher: str | None = Field(default=None, max_length=150)
    publication_date: date | None = None
    model_config = ConfigDict(extra='forbid')

    @field_validator('title', 'genre', 'publisher', 'description', mode='before')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('author_ids')
    @classmethod
    def validate_authors(cls, values):
        if any(value <= 0 for value in values) or len(set(values)) != len(values):
            raise ValueError('Les identifiants des auteurs doivent être positifs et distincts')
        return values

    @field_validator('isbn', mode='before')
    @classmethod
    def normalize_isbn(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('ISBN invalide')
        value = value.replace('-', '').replace(' ', '').upper()
        if len(value) == 10 and value[:9].isascii() and value[:9].isdigit():
            if value[-1] not in '0123456789X':
                raise ValueError('ISBN invalide')
            digits = [int(c) if c != 'X' else 10 for c in value]
            if sum((10 - i) * digit for i, digit in enumerate(digits)) % 11 != 0:
                raise ValueError('Clé ISBN invalide')
            # Une édition ne doit pas être dupliquée sous ses ISBN-10 et ISBN-13.
            prefix = '978' + value[:9]
            checksum = (10 - sum(int(c) * (1 if i % 2 == 0 else 3)
                                 for i, c in enumerate(prefix)) % 10) % 10
            return prefix + str(checksum)
        if len(value) != 13 or not value.isascii() or not value.isdigit() or not value.startswith(('978', '979')):
            raise ValueError('ISBN invalide')
        if sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(value)) % 10 != 0:
            raise ValueError('Clé ISBN invalide')
        return value


class BookResponse(BaseModel):
    id: int
    title: str
    genre: str
    authors: list[AuthorResponse]
    isbn: str | None
    description: str | None
    publisher: str | None
    publication_date: date | None
    is_active: bool
    is_available: bool


class AdminBookResponse(BookResponse):
    total_stock: int
    available_stock: int


CopyStatus = Literal['IN_SERVICE', 'DAMAGED', 'LOST', 'WITHDRAWN']


class BookCopyCreate(BaseModel):
    inventory_code: str = Field(min_length=1, max_length=50)
    service_status: CopyStatus = 'IN_SERVICE'
    model_config = ConfigDict(extra='forbid')

    @field_validator('inventory_code', mode='before')
    @classmethod
    def normalize_code(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class BookCopyUpdate(BaseModel):
    service_status: CopyStatus
    model_config = ConfigDict(extra='forbid')


class BookCopyResponse(BookCopyCreate):
    id: int
    book_id: int
    model_config = ConfigDict(from_attributes=True)


class LoanCreate(BaseModel):
    book_id: int = Field(gt=0)
    model_config = ConfigDict(extra='forbid')


class LoanResponse(BaseModel):
    id: int
    user_id: int
    copy_id: int
    book_id: int
    book_title: str
    inventory_code: str
    borrowed_at: datetime
    closed_at: datetime | None
    closure_reason: Literal['RETURNED', 'LOST'] | None
    closed_by_id: int | None
    is_active: bool
