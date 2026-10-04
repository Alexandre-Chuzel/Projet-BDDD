from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import models
import schemas
from database import get_db
from security import current_user, require_admin

router = APIRouter(tags=['Catalogue'])


def commit_catalogue(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='ISBN, numéro d’inventaire ou référence en conflit') from None


def get_author(db, author_id, lock=False):
    statement = select(models.Author).where(models.Author.id == author_id)
    if lock:
        statement = statement.with_for_update()
    author = db.scalar(statement.execution_options(populate_existing=True))
    if author is None:
        raise HTTPException(status_code=404, detail='Auteur introuvable')
    return author


@router.get('/authors', response_model=list[schemas.AuthorResponse])
def list_authors(
    name: str | None = Query(default=None, min_length=1, max_length=200),
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
    user: models.User = Depends(current_user), db: Session = Depends(get_db),
):
    statement = select(models.Author).order_by(models.Author.id)
    if name:
        full_name = models.Author.first_name + ' ' + models.Author.last_name
        statement = statement.where(func.lower(full_name).contains(name.strip().lower(), autoescape=True))
    return db.scalars(statement.offset(offset).limit(limit)).all()


@router.get('/authors/{author_id}', response_model=schemas.AuthorResponse)
def read_author(author_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return get_author(db, author_id)


@router.post('/authors', response_model=schemas.AuthorResponse, status_code=201)
def create_author(data: schemas.AuthorCreate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    author = models.Author(first_name=data.first_name, last_name=data.last_name)
    db.add(author)
    commit_catalogue(db)
    db.refresh(author)
    return author


@router.put('/authors/{author_id}', response_model=schemas.AuthorResponse)
def update_author(author_id: int, data: schemas.AuthorCreate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    author = get_author(db, author_id, lock=True)
    author.first_name = data.first_name
    author.last_name = data.last_name
    commit_catalogue(db)
    db.refresh(author)
    return author


@router.delete('/authors/{author_id}')
def delete_author(author_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    author = get_author(db, author_id, lock=True)
    references = db.scalar(select(func.count()).select_from(models.book_authors).where(models.book_authors.c.author_id == author_id))
    if references:
        raise HTTPException(status_code=409, detail='Cet auteur est associé à un livre')
    db.delete(author)
    commit_catalogue(db)
    return {'message': 'Auteur supprimé'}


def get_book(db, book_id, lock=False):
    statement = select(models.Book).where(models.Book.id == book_id).options(selectinload(models.Book.authors))
    if lock:
        statement = statement.with_for_update()
    book = db.scalar(statement.execution_options(populate_existing=True))
    if book is None:
        raise HTTPException(status_code=404, detail='Livre introuvable')
    return book


def get_authors(db, author_ids):
    # Empêche la suppression d'un auteur entre sa vérification et son association.
    authors = db.scalars(select(models.Author).where(models.Author.id.in_(author_ids)).order_by(models.Author.id).with_for_update()).all()
    if len(authors) != len(author_ids):
        raise HTTPException(status_code=404, detail='Un auteur est introuvable')
    return authors


def book_response(db, book, user):
    active_loan = select(models.Loan.id).where(
        models.Loan.copy_id == models.BookCopy.id, models.Loan.closed_at.is_(None),
    ).exists()
    available_copy = and_(models.BookCopy.service_status == 'IN_SERVICE', ~active_loan)
    # Une seule requête garde les deux quantités cohérentes entre elles.
    total, available = db.execute(select(
        func.count(models.BookCopy.id),
        func.coalesce(func.sum(case((available_copy, 1), else_=0)), 0),
    ).where(models.BookCopy.book_id == book.id, models.BookCopy.service_status != 'WITHDRAWN')).one()
    data = {
        'id': book.id, 'title': book.title, 'genre': book.genre, 'authors': book.authors,
        'isbn': book.isbn, 'description': book.description, 'publisher': book.publisher,
        'publication_date': book.publication_date, 'is_active': book.is_active,
        'is_available': book.is_active and available > 0,
    }
    if user.role == 'ADMIN':
        return schemas.AdminBookResponse(**data, total_stock=total, available_stock=available)
    return schemas.BookResponse(**data)


@router.get('/books', response_model=list[schemas.AdminBookResponse | schemas.BookResponse])
def list_books(
    title: str | None = Query(default=None, min_length=1, max_length=200),
    author: str | None = Query(default=None, min_length=1, max_length=200),
    genre: str | None = Query(default=None, min_length=1, max_length=100),
    include_inactive: bool = False, offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    user: models.User = Depends(current_user), db: Session = Depends(get_db),
):
    if include_inactive and user.role != 'ADMIN':
        raise HTTPException(status_code=403, detail='Accès réservé aux administrateurs')
    statement = select(models.Book).options(selectinload(models.Book.authors)).order_by(models.Book.id)
    if not include_inactive:
        statement = statement.where(models.Book.is_active == True)
    if title:
        statement = statement.where(func.lower(models.Book.title).contains(title.strip().lower(), autoescape=True))
    if genre:
        statement = statement.where(func.lower(models.Book.genre).contains(genre.strip().lower(), autoescape=True))
    if author:
        full_name = models.Author.first_name + ' ' + models.Author.last_name
        statement = statement.where(models.Book.authors.any(func.lower(full_name).contains(author.strip().lower(), autoescape=True)))
    books = db.scalars(statement.offset(offset).limit(limit)).all()
    return [book_response(db, book, user) for book in books]


@router.get('/books/{book_id}', response_model=schemas.AdminBookResponse | schemas.BookResponse)
def read_book(book_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    book = get_book(db, book_id)
    if not book.is_active and user.role != 'ADMIN':
        raise HTTPException(status_code=404, detail='Livre introuvable')
    return book_response(db, book, user)


@router.post('/books', response_model=schemas.AdminBookResponse, status_code=201)
def create_book(data: schemas.BookCreate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    authors = get_authors(db, data.author_ids)
    book = models.Book(**data.model_dump(exclude={'author_ids'}), authors=authors)
    db.add(book)
    commit_catalogue(db)
    db.refresh(book)
    return book_response(db, book, admin)


@router.put('/books/{book_id}', response_model=schemas.AdminBookResponse)
def update_book(book_id: int, data: schemas.BookCreate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    book = get_book(db, book_id, lock=True)
    authors = get_authors(db, data.author_ids)
    book.title = data.title
    book.genre = data.genre
    book.isbn = data.isbn
    book.description = data.description
    book.publisher = data.publisher
    book.publication_date = data.publication_date
    book.authors = authors
    commit_catalogue(db)
    db.refresh(book)
    return book_response(db, book, admin)


@router.delete('/books/{book_id}')
def delete_book(book_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    book = get_book(db, book_id, lock=True)
    active_loan = db.scalar(select(models.Loan.id).join(models.BookCopy, models.Loan.copy_id == models.BookCopy.id).where(
        models.BookCopy.book_id == book.id, models.Loan.closed_at.is_(None),
    ))
    if active_loan is not None:
        raise HTTPException(status_code=409, detail='Ce livre possède des emprunts en cours')
    book.is_active = False
    db.commit()
    return {'message': 'Livre désactivé'}


@router.post('/books/{book_id}/restore', response_model=schemas.AdminBookResponse)
def restore_book(book_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    book = get_book(db, book_id, lock=True)
    book.is_active = True
    db.commit()
    return book_response(db, book, admin)


def get_copy(db, book_id, copy_id):
    copy = db.scalar(select(models.BookCopy).where(
        models.BookCopy.id == copy_id, models.BookCopy.book_id == book_id,
    ).with_for_update().execution_options(populate_existing=True))
    if copy is None:
        raise HTTPException(status_code=404, detail='Exemplaire introuvable pour ce livre')
    return copy


def ensure_copy_not_borrowed(db, copy):
    active_loan = db.scalar(select(models.Loan.id).where(models.Loan.copy_id == copy.id, models.Loan.closed_at.is_(None)))
    if active_loan is not None:
        raise HTTPException(status_code=409, detail='Cet exemplaire est emprunté ; clôturer son emprunt avant de modifier son état')


@router.get('/books/{book_id}/copies', response_model=list[schemas.BookCopyResponse])
def list_copies(
    book_id: int, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
    admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    get_book(db, book_id)
    return db.scalars(select(models.BookCopy).where(models.BookCopy.book_id == book_id).order_by(models.BookCopy.id).offset(offset).limit(limit)).all()


@router.post('/books/{book_id}/copies', response_model=schemas.BookCopyResponse, status_code=201)
def create_copy(book_id: int, data: schemas.BookCopyCreate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    book = get_book(db, book_id, lock=True)
    if not book.is_active:
        raise HTTPException(status_code=409, detail='Réactiver le livre avant d’ajouter un exemplaire')
    copy = models.BookCopy(book_id=book.id, inventory_code=data.inventory_code, service_status=data.service_status)
    db.add(copy)
    commit_catalogue(db)
    db.refresh(copy)
    return copy


@router.patch('/books/{book_id}/copies/{copy_id}', response_model=schemas.BookCopyResponse)
def update_copy(book_id: int, copy_id: int, data: schemas.BookCopyUpdate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    get_book(db, book_id, lock=True)
    copy = get_copy(db, book_id, copy_id)
    ensure_copy_not_borrowed(db, copy)
    copy.service_status = data.service_status
    db.commit()
    db.refresh(copy)
    return copy


@router.delete('/books/{book_id}/copies/{copy_id}', response_model=schemas.BookCopyResponse)
def withdraw_copy(book_id: int, copy_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    get_book(db, book_id, lock=True)
    copy = get_copy(db, book_id, copy_id)
    ensure_copy_not_borrowed(db, copy)
    copy.service_status = 'WITHDRAWN'
    db.commit()
    db.refresh(copy)
    return copy
