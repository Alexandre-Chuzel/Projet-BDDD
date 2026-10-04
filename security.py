from datetime import datetime, timedelta, timezone
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from database import get_db
from models import User

ALGORITHM = 'HS256'
TOKEN_EXPIRE_MINUTES = 15
password = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')


def secret_key() -> str:
    key = os.getenv('SECRET_KEY', '')
    if len(key.encode('utf-8')) < 32:
        raise RuntimeError('SECRET_KEY doit contenir au moins 32 octets.')
    return key


def create_token(user_id: int) -> str:
    return jwt.encode(
        {
            'sub': str(user_id),
            'exp': datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
        },
        secret_key(),
        algorithm=ALGORITHM,
    )


def current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Authentification invalide ou expirée',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = jwt.decode(
            token, secret_key(), algorithms=[ALGORITHM],
            options={'require': ['sub', 'exp']},
        )
        subject = payload['sub']
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal():
            raise jwt.InvalidTokenError('Identifiant invalide')
        user_id = int(subject)
        if user_id <= 0:
            raise jwt.InvalidTokenError('Identifiant invalide')
    except (jwt.InvalidTokenError, ValueError):
        raise credentials_error from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user
