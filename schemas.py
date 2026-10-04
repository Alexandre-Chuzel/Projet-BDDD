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
