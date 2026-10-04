from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from security import create_token, current_user, password

app = FastAPI(title='Bibliothèque', version='0.1.0')
root_path = Path(__file__).resolve().parent
app.mount('/static', StaticFiles(directory=root_path / 'static'), name='static')
templates = Jinja2Templates(directory=root_path / 'templates')

# Évite une réponse beaucoup plus rapide lorsque le compte n'existe pas.
dummy_password_hash = password.hash('unused-login-password')


@app.post('/login', tags=['Authentification'])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    user = db.scalar(select(models.User).where(func.lower(models.User.email) == email))
    try:
        valid_password = password.verify(
            form.password, user.password if user else dummy_password_hash,
        )
    except UnknownHashError:
        valid_password = False
    if user is None or not valid_password:
        raise HTTPException(
            status_code=401, detail='Email ou mot de passe incorrect',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return {'access_token': create_token(user.id), 'token_type': 'bearer'}


@app.get('/private', tags=['Authentification'])
def private(user: models.User = Depends(current_user)):
    return {'message': f'Bonjour {user.name}'}


@app.get('/', include_in_schema=False)
def read_root():
    return RedirectResponse(url='/static/index.html')


@app.get('/items/{item_id}', include_in_schema=False)
def read_item(item_id: int, request: Request, q: str | None = None):
    return templates.TemplateResponse(
        request=request, name='index.html', context={'item_id': item_id, 'q': q},
    )


def commit_user(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Cet email est déjà utilisé') from None


@app.post('/users', response_model=schemas.UserResponse, status_code=201, tags=['Utilisateurs'])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(models.User.id).where(func.lower(models.User.email) == user.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail='Cet email est déjà utilisé')
    new_user = models.User(name=user.name, email=user.email, password=password.hash(user.password))
    db.add(new_user)
    commit_user(db)
    db.refresh(new_user)
    return new_user


def own_account(user_id: int, user: models.User):
    if user_id != user.id:
        raise HTTPException(status_code=403, detail='Accès réservé à votre compte')


@app.get('/users/{user_id}', response_model=schemas.UserResponse, tags=['Utilisateurs'])
def get_user(user_id: int, user: models.User = Depends(current_user)):
    own_account(user_id, user)
    return user


@app.put('/users/{user_id}', response_model=schemas.UserResponse, tags=['Utilisateurs'])
def update_user(
    user_id: int, user_data: schemas.UserCreate,
    user: models.User = Depends(current_user), db: Session = Depends(get_db),
):
    own_account(user_id, user)
    existing = db.scalar(select(models.User.id).where(
        func.lower(models.User.email) == user_data.email, models.User.id != user.id,
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail='Cet email est déjà utilisé')
    user.name = user_data.name
    user.email = user_data.email
    user.password = password.hash(user_data.password)
    commit_user(db)
    db.refresh(user)
    return user


@app.delete('/users/{user_id}', tags=['Utilisateurs'])
def delete_user(
    user_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db),
):
    own_account(user_id, user)
    db.delete(user)
    db.commit()
    return {'message': 'Utilisateur supprimé'}
