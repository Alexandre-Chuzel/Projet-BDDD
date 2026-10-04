from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
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
from catalogue import router as catalogue_router
from loans import router as loans_router
from database import get_db
from security import create_token, current_user, password, require_admin

app = FastAPI(title='Bibliothèque', version='0.4.0')
app.include_router(catalogue_router)
app.include_router(loans_router)
root_path = Path(__file__).resolve().parent
app.mount('/static', StaticFiles(directory=root_path / 'static'), name='static')
templates = Jinja2Templates(directory=root_path / 'templates')
dummy_password_hash = password.hash('unused-login-password')


@app.post('/login', tags=['Authentification'])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    user = db.scalar(select(models.User).where(func.lower(models.User.email) == email))
    try:
        valid_password = password.verify(
            form.password, user.password_hash if user else dummy_password_hash,
        )
    except UnknownHashError:
        valid_password = False
    if user is None or not valid_password or not user.is_active:
        raise HTTPException(
            status_code=401, detail='Email ou mot de passe incorrect',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return {'access_token': create_token(user.id), 'token_type': 'bearer'}


@app.get('/private', tags=['Authentification'])
def private(user: models.User = Depends(current_user)):
    return {'message': f'Bonjour {user.first_name}'}


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


def check_email(db: Session, email: str, user_id: int | None = None):
    statement = select(models.User.id).where(func.lower(models.User.email) == email)
    if user_id is not None:
        statement = statement.where(models.User.id != user_id)
    if db.scalar(statement) is not None:
        raise HTTPException(status_code=409, detail='Cet email est déjà utilisé')


def add_user(data: schemas.UserCreate, db: Session, role: str = 'USER'):
    check_email(db, data.email)
    user = models.User(
        first_name=data.first_name, last_name=data.last_name, email=data.email,
        phone=data.phone, password_hash=password.hash(data.password), role=role,
    )
    db.add(user)
    commit_user(db)
    db.refresh(user)
    return user


@app.post('/users', response_model=schemas.UserResponse, status_code=201, tags=['Utilisateurs'])
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    # Le rôle ne peut pas être choisi lors d'une inscription publique.
    return add_user(data, db)


@app.post('/admin/users', response_model=schemas.UserResponse, status_code=201, tags=['Administration'])
def create_user_by_admin(
    data: schemas.AdminUserCreate, admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return add_user(data, db, data.role)


@app.get('/users/me', response_model=schemas.UserResponse, tags=['Utilisateurs'])
def get_my_account(user: models.User = Depends(current_user)):
    return user


@app.get('/users', response_model=list[schemas.UserResponse], tags=['Administration'])
def get_users(
    include_inactive: bool = False, offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    statement = select(models.User).order_by(models.User.id)
    if not include_inactive:
        statement = statement.where(models.User.is_active == True)
    return db.scalars(statement.offset(offset).limit(limit)).all()


def get_account(db: Session, user_id: int):
    user = db.get(models.User, user_id, populate_existing=True)
    if user is None:
        raise HTTPException(status_code=404, detail='Utilisateur introuvable')
    return user


@app.get('/users/{user_id}', response_model=schemas.UserResponse, tags=['Utilisateurs'])
def get_user(
    user_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db),
):
    if user.role != 'ADMIN' and user_id != user.id:
        raise HTTPException(status_code=403, detail='Accès réservé à votre compte')
    return get_account(db, user_id)


def lock_accounts(db: Session, admin: models.User):
    # Le verrou empêche deux administrateurs de supprimer/dégrader leurs comptes
    # en même temps. Tous prennent les verrous dans le même ordre.
    db.scalars(select(models.User.id).order_by(models.User.id).with_for_update()).all()
    db.refresh(admin)
    require_admin(admin)


def protect_last_admin(db: Session, user: models.User):
    if user.role == 'ADMIN' and user.is_active:
        other_admins = db.scalar(select(func.count()).select_from(models.User).where(
            models.User.role == 'ADMIN', models.User.is_active == True,
            models.User.id != user.id,
        ))
        if other_admins == 0:
            raise HTTPException(status_code=409, detail='Le dernier administrateur actif doit être conservé')


@app.put('/users/{user_id}', response_model=schemas.UserResponse, tags=['Administration'])
def update_user(
    user_id: int, data: schemas.UserUpdate,
    admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    lock_accounts(db, admin)
    user = get_account(db, user_id)
    if data.role == 'USER':
        protect_last_admin(db, user)
    check_email(db, data.email, user.id)
    user.first_name = data.first_name
    user.last_name = data.last_name
    user.email = data.email
    user.phone = data.phone
    if data.password is not None:
        user.password_hash = password.hash(data.password)
    if data.role is not None:
        user.role = data.role
    commit_user(db)
    db.refresh(user)
    return user


@app.patch('/users/{user_id}/blacklist', response_model=schemas.UserResponse, tags=['Administration'])
def update_blacklist(
    user_id: int, data: schemas.BlacklistUpdate,
    admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    user = get_account(db, user_id)
    user.is_blacklisted = data.is_blacklisted
    db.commit()
    db.refresh(user)
    return user


@app.delete('/users/{user_id}', tags=['Administration'])
def delete_user(
    user_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    lock_accounts(db, admin)
    user = get_account(db, user_id)
    active_loan = db.scalar(select(models.Loan.id).where(models.Loan.user_id == user.id, models.Loan.closed_at.is_(None)))
    if active_loan is not None:
        raise HTTPException(status_code=409, detail='Cet utilisateur possède des emprunts en cours')
    protect_last_admin(db, user)
    user.is_active = False
    db.commit()
    return {'message': 'Utilisateur désactivé'}


@app.post('/users/{user_id}/restore', response_model=schemas.UserResponse, tags=['Administration'])
def restore_user(
    user_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    lock_accounts(db, admin)
    user = get_account(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user
