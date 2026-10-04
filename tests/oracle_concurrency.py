"""Test manuel sur Oracle : deux demandes pour le dernier exemplaire.

À lancer depuis le projet : python tests/oracle_concurrency.py
Les données dédiées au test sont créées puis supprimées dans le bloc finally.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import engine
from loans import borrow_book, return_book, utc_now
from models import Author, Book, BookCopy, Loan, User, book_authors
from schemas import LoanCreate
from security import password


def main():
    if engine.dialect.name != 'oracle':
        raise SystemExit('Ce test doit utiliser la base Oracle du projet.')
    suffix = uuid4().hex
    user_ids = []
    book_id = author_id = copy_id = None
    with Session(engine) as db:
        counts_before = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                         for model in [User, Author, Book, BookCopy, Loan]}
    try:
        with Session(engine) as db:
            users = [User(first_name='Test', last_name='Concurrence',
                          email=f'race-{suffix}-{i}@example.com',
                          password_hash=password.hash('test-oracle-password')) for i in range(2)]
            author = Author(first_name='Test', last_name='Concurrence')
            book = Book(title='Test concurrence ' + suffix, genre='Test', authors=[author])
            copy = BookCopy(book=book, inventory_code='RACE-' + suffix.upper())
            db.add_all([*users, copy])
            db.flush()
            user_ids = [user.id for user in users]
            book_id, author_id, copy_id = book.id, author.id, copy.id
            db.commit()

        barrier = Barrier(2)
        def attempt(user_id):
            with Session(engine, autoflush=False) as db:
                user = db.get(User, user_id)
                barrier.wait(timeout=10)
                try:
                    loan = borrow_book(LoanCreate(book_id=book_id), user=user, db=db)
                    return 201, loan.id, user_id
                except HTTPException as error:
                    db.rollback()
                    return error.status_code, None, user_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt, user_id) for user_id in user_ids]
            results = [future.result(timeout=30) for future in futures]
        assert sorted(result[0] for result in results) == [201, 409], 'Un seul emprunt doit réussir'
        winner = next(result for result in results if result[0] == 201)
        with Session(engine) as db:
            active_count = db.scalar(select(func.count()).select_from(Loan).where(Loan.copy_id == copy_id, Loan.closed_at.is_(None)))
            assert active_count == 1
            # Vérifie aussi la contrainte unique en contournant les routes.
            db.add(Loan(user_id=user_ids[0], copy_id=copy_id, borrowed_at=utc_now()))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            else:
                raise AssertionError('La base doit refuser un deuxième emprunt actif')
        with Session(engine, autoflush=False) as db:
            returned = return_book(winner[1], user=db.get(User, winner[2]), db=db)
            assert returned.closure_reason == 'RETURNED'
        with Session(engine, autoflush=False) as db:
            new_loan = borrow_book(LoanCreate(book_id=book_id), user=db.get(User, user_ids[0]), db=db)
            assert new_loan.copy_id == copy_id
        print('Oracle : un succès 201, un refus 409 ; contrainte unique, retour et réemprunt validés.')
    finally:
        # Seuls les identifiants créés par ce test sont supprimés.
        with Session(engine) as db:
            if copy_id is not None:
                db.execute(delete(Loan).where(Loan.copy_id == copy_id))
                db.execute(delete(BookCopy).where(BookCopy.id == copy_id))
            if book_id is not None:
                db.execute(delete(book_authors).where(book_authors.c.book_id == book_id))
                db.execute(delete(Book).where(Book.id == book_id))
            if author_id is not None:
                db.execute(delete(Author).where(Author.id == author_id))
            if user_ids:
                db.execute(delete(User).where(User.id.in_(user_ids)))
            db.commit()
        with Session(engine) as db:
            counts_after = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                            for model in [User, Author, Book, BookCopy, Loan]}
            assert counts_before == counts_after, 'Les données dédiées au test doivent être retirées'
        print('Données du test supprimées ; quantités initiales conservées.')


if __name__ == '__main__':
    main()
