from datetime import datetime, timedelta, timezone

import jwt

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
import models
import schemas
from security import (
    create_token,
    current_user,
    password
)
from database import engine, get_db


app = FastAPI()

@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user:
        raise HTTPException(
            status_code=401,
            detail="login incorrect"
        )
    if not password.verify(form.password, user.password):
        raise HTTPException(
            status_code=401,
            detail="mot de passe incorrect"
        )

    token = create_token(form.email)

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.get("/private")
def private(username: str = Depends(current_user)):
    return {"message": f"Bonjour {username}"}

models.Base.metadata.create_all(bind=engine)


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(
    directory="templates"
)



@app.get("/")
def read_root():
    return RedirectResponse(
        url="/static/index.html"
    )

@app.get("/items/{item_id}")
def read_item(
    item_id: int,
    request: Request,
    q: str | None = None
):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "item_id": item_id,
            "q": q
        }
    )


@app.post(
    "/users",
    response_model=schemas.UserResponse
)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    password_hashed = password.hash(
        user.password
    )
    new_user = models.User(
        name=user.name,
        email=user.email,
        password=password_hashed
    )

    db.add(new_user)

    db.commit()

    db.refresh(new_user)

    return new_user


@app.get(
    "/users/{user_id}",
    response_model=schemas.UserResponse
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = db.get(
        models.User,
        user_id
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable"
        )

    return user


@app.get(
    "/users",
    response_model=list[schemas.UserResponse]
)
def get_users(
    db: Session = Depends(get_db)
):

    statement = select(models.User)

    users = db.scalars(
        statement
    ).all()

    return users



@app.put(
    "/users/{user_id}",
    response_model=schemas.UserResponse
)
def update_user(
    user_id: int,
    user_data: schemas.UserCreate,
    db: Session = Depends(get_db)
):

    user = db.get(
        models.User,
        user_id
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable"
        )

    user.name = user_data.name
    user.email = user_data.email

    db.commit()

    db.refresh(user)

    return user



@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = db.get(
        models.User,
        user_id
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable"
        )

    db.delete(user)

    db.commit()

    return {
        "message": "Utilisateur supprimé"
    }