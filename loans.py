from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import models
import schemas
from catalogue import get_book, get_copy
from database import get_db
from security import current_user, require_admin

router = APIRouter(tags=['Emprunts'])


def utc_now():
    # Les dates sont stockées en UTC, sans fuseau dans les colonnes Oracle.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def loan_response(loan):
    return schemas.LoanResponse(
        id=loan.id, user_id=loan.user_id, copy_id=loan.copy_id,
        book_id=loan.copy.book_id, book_title=loan.copy.book.title,
        inventory_code=loan.copy.inventory_code, borrowed_at=loan.borrowed_at,
        closed_at=loan.closed_at, closure_reason=loan.closure_reason,
        closed_by_id=loan.closed_by_id, is_active=loan.closed_at is None,
    )


def lock_user(db, user_id):
    user = db.scalar(select(models.User).where(models.User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail='Compte désactivé', headers={'WWW-Authenticate': 'Bearer'})
    return user


@router.post('/loans', response_model=schemas.LoanResponse, status_code=201)
def borrow_book(data: schemas.LoanCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    # Ordre des verrous : utilisateur, livre, exemplaire.
    user = lock_user(db, user.id)
    return create_loan(db, user, data.book_id)


def create_loan(db, user, book_id):
    if user.is_blacklisted:
        raise HTTPException(status_code=403, detail='Les utilisateurs sur liste noire ne peuvent pas emprunter')
    book = get_book(db, book_id, lock=True)
    if not book.is_active:
        raise HTTPException(status_code=409, detail='Ce livre est désactivé')
    active_loan = select(models.Loan.id).where(
        models.Loan.copy_id == models.BookCopy.id, models.Loan.closed_at.is_(None),
    ).exists()
    copy_id = db.scalar(select(func.min(models.BookCopy.id)).where(
        models.BookCopy.book_id == book.id, models.BookCopy.service_status == 'IN_SERVICE', ~active_loan,
    ))
    if copy_id is None:
        raise HTTPException(status_code=409, detail='Aucun exemplaire disponible')
    copy = get_copy(db, book.id, copy_id)
    loan = models.Loan(user_id=user.id, copy_id=copy.id, borrowed_at=utc_now())
    db.add(loan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Cet exemplaire ne peut plus être emprunté') from None
    db.refresh(loan)
    return loan_response(loan)


def lock_admin_and_borrower(db, admin_id, user_id):
    # Un ordre commun évite que deux opérations attendent chacune le compte de l'autre.
    users = db.scalars(select(models.User).where(models.User.id.in_([admin_id, user_id]))
                       .order_by(models.User.id).with_for_update()
                       .execution_options(populate_existing=True)).all()
    accounts = {user.id: user for user in users}
    admin = accounts.get(admin_id)
    if admin is None or not admin.is_active or admin.role != 'ADMIN':
        raise HTTPException(status_code=403, detail='Accès réservé aux administrateurs')
    borrower = accounts.get(user_id)
    if borrower is None:
        raise HTTPException(status_code=404, detail='Utilisateur introuvable')
    return borrower


@router.post('/admin/loans', response_model=schemas.LoanResponse, status_code=201)
def admin_borrow_book(data: schemas.AdminLoanCreate, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    borrower = lock_admin_and_borrower(db, admin.id, data.user_id)
    if not borrower.is_active:
        raise HTTPException(status_code=409, detail='Ce compte est désactivé')
    return create_loan(db, borrower, data.book_id)


def find_loan(db, loan_id, lock=False):
    statement = select(models.Loan).where(models.Loan.id == loan_id)
    if lock:
        statement = statement.with_for_update()
    loan = db.scalar(statement.execution_options(populate_existing=True))
    if loan is None:
        raise HTTPException(status_code=404, detail='Emprunt introuvable')
    return loan


@router.post('/loans/{loan_id}/return', response_model=schemas.LoanResponse)
def return_book(loan_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    loan = find_loan(db, loan_id)
    if loan.user_id != user.id:
        raise HTTPException(status_code=403, detail='Vous ne pouvez rendre que vos propres emprunts')
    user = lock_user(db, user.id)
    return close_loan(db, loan, user.id, 'IN_SERVICE')


def close_loan(db, loan, actor_id, copy_status):
    get_book(db, loan.copy.book_id, lock=True)
    copy = get_copy(db, loan.copy.book_id, loan.copy_id)
    loan = find_loan(db, loan.id, lock=True)
    if loan.closed_at is not None:
        raise HTTPException(status_code=409, detail='Cet emprunt est déjà clôturé')
    loan.closed_at = utc_now()
    loan.closure_reason = 'LOST' if copy_status == 'LOST' else 'RETURNED'
    loan.closed_by_id = actor_id
    copy.service_status = copy_status
    try:
        # L'emprunt et l'état de l'exemplaire changent dans la même transaction.
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='La clôture ne peut pas être enregistrée') from None
    db.refresh(loan)
    return loan_response(loan)


@router.post('/admin/loans/{loan_id}/close', response_model=schemas.LoanResponse)
def admin_close_loan(loan_id: int, data: schemas.LoanClosure, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    loan = find_loan(db, loan_id)
    # La clôture reste possible pour un compte sur liste noire ou désactivé.
    lock_admin_and_borrower(db, admin.id, loan.user_id)
    return close_loan(db, loan, admin.id, data.copy_status)


def list_loan_responses(db, statement, active_only, offset, limit):
    if active_only:
        statement = statement.where(models.Loan.closed_at.is_(None))
    statement = statement.options(selectinload(models.Loan.copy).selectinload(models.BookCopy.book))
    statement = statement.order_by(models.Loan.borrowed_at.desc(), models.Loan.id.desc()).offset(offset).limit(limit)
    return [loan_response(loan) for loan in db.scalars(statement).all()]


@router.get('/loans/me', response_model=list[schemas.LoanResponse])
def my_loans(
    active_only: bool = False, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
    user: models.User = Depends(current_user), db: Session = Depends(get_db),
):
    statement = select(models.Loan).where(models.Loan.user_id == user.id)
    return list_loan_responses(db, statement, active_only, offset, limit)


@router.get('/loans', response_model=list[schemas.LoanResponse])
def all_loans(
    user_id: int | None = Query(default=None, gt=0), book_id: int | None = Query(default=None, gt=0),
    active_only: bool = False, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
    admin: models.User = Depends(require_admin), db: Session = Depends(get_db),
):
    statement = select(models.Loan)
    if user_id is not None:
        statement = statement.where(models.Loan.user_id == user_id)
    if book_id is not None:
        statement = statement.join(models.BookCopy).where(models.BookCopy.book_id == book_id)
    return list_loan_responses(db, statement, active_only, offset, limit)


@router.get('/loans/{loan_id}', response_model=schemas.LoanResponse)
def read_loan(loan_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    loan = find_loan(db, loan_id)
    if user.role != 'ADMIN' and loan.user_id != user.id:
        raise HTTPException(status_code=403, detail='Accès réservé à vos emprunts')
    return loan_response(loan)
