from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from loans import utc_now
from models import Author, Book, BookCopy, Loan, User
from security import password


@pytest.fixture
def library(client, db):
    admin=User(first_name='Admin',last_name='Test',email='admin@example.com',password_hash=password.hash('secret-password'),role='ADMIN')
    alice=User(first_name='Alice',last_name='Test',email='alice@example.com',password_hash=password.hash('secret-password'))
    bob=User(first_name='Bob',last_name='Test',email='bob@example.com',password_hash=password.hash('secret-password'))
    author=Author(first_name='Victor',last_name='Hugo')
    book=Book(title='Les Misérables',genre='Roman',authors=[author])
    db.add_all([admin,alice,bob,book]); db.commit()
    copies=[BookCopy(book_id=book.id,inventory_code='EX-001'),BookCopy(book_id=book.id,inventory_code='EX-002')]
    db.add_all(copies); db.commit()
    def headers(user):
        response=client.post('/login',data={'username':user.email,'password':'secret-password'})
        assert response.status_code==200
        return {'Authorization':'Bearer '+response.json()['access_token']}
    return {'admin':admin,'alice':alice,'bob':bob,'book':book,'copies':copies,
            'admin_headers':headers(admin),'alice_headers':headers(alice),'bob_headers':headers(bob)}


def borrow(client, library, user='alice'):
    response=client.post('/loans',headers=library[user+'_headers'],json={'book_id':library['book'].id})
    assert response.status_code==201
    return response.json()


def stock(client, library):
    return client.get(f'/books/{library["book"].id}',headers=library['admin_headers']).json()


def test_two_copies_allow_two_loans_then_refuse_third(client, library):
    first=borrow(client,library)
    assert first['user_id']==library['alice'].id and first['is_active'] is True
    assert stock(client,library)['available_stock']==1
    second=borrow(client,library,'bob')
    assert second['copy_id']!=first['copy_id']
    assert stock(client,library)['available_stock']==0
    assert stock(client,library)['total_stock']==2
    assert stock(client,library)['is_available'] is False
    response=client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id})
    assert response.status_code==409


def test_return_releases_one_copy_and_retains_history(client, library, db):
    loan=borrow(client,library)
    response=client.post(f'/loans/{loan["id"]}/return',headers=library['alice_headers'])
    assert response.status_code==200
    data=response.json()
    assert data['is_active'] is False and data['closure_reason']=='RETURNED'
    assert data['closed_by_id']==library['alice'].id
    assert data['closed_at']>=data['borrowed_at']
    assert stock(client,library)['available_stock']==2
    assert db.get(Loan,loan['id']) is not None
    assert len(client.get('/loans/me',headers=library['alice_headers']).json())==1
    assert client.get('/loans/me?active_only=true',headers=library['alice_headers']).json()==[]
    again=borrow(client,library)
    assert again['copy_id']==loan['copy_id'] and again['id']!=loan['id']


def test_cannot_return_another_users_loan_or_return_twice(client, library):
    loan=borrow(client,library)
    assert client.post(f'/loans/{loan["id"]}/return',headers=library['bob_headers']).status_code==403
    assert client.post(f'/loans/{loan["id"]}/return',headers=library['admin_headers']).status_code==403
    assert stock(client,library)['available_stock']==1
    assert client.post(f'/loans/{loan["id"]}/return',headers=library['alice_headers']).status_code==200
    assert client.post(f'/loans/{loan["id"]}/return',headers=library['alice_headers']).status_code==409
    assert stock(client,library)['available_stock']==2


def test_blacklisted_user_can_return_but_not_borrow(client, library):
    loan=borrow(client,library)
    response=client.patch(f'/users/{library["alice"].id}/blacklist',headers=library['admin_headers'],json={'is_blacklisted':True})
    assert response.status_code==200
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id}).status_code==403
    assert client.get('/loans/me',headers=library['alice_headers']).status_code==200
    assert client.post(f'/loans/{loan["id"]}/return',headers=library['alice_headers']).status_code==200


def test_cannot_deactivate_user_book_or_change_borrowed_copy(client, library):
    loan=borrow(client,library)
    assert client.delete(f'/users/{library["alice"].id}',headers=library['admin_headers']).status_code==409
    assert client.delete(f'/books/{library["book"].id}',headers=library['admin_headers']).status_code==409
    copy_url=f'/books/{library["book"].id}/copies/{loan["copy_id"]}'
    assert client.delete(copy_url,headers=library['admin_headers']).status_code==409
    assert client.patch(copy_url,headers=library['admin_headers'],json={'service_status':'LOST'}).status_code==409
    assert client.post(f'/loans/{loan["id"]}/return',headers=library['alice_headers']).status_code==200
    assert client.delete(copy_url,headers=library['admin_headers']).status_code==200
    assert client.delete(f'/users/{library["alice"].id}',headers=library['admin_headers']).status_code==200
    assert client.delete(f'/books/{library["book"].id}',headers=library['admin_headers']).status_code==200
    history=client.get('/loans',headers=library['admin_headers']).json()
    assert len(history)==1 and history[0]['id']==loan['id']


def test_history_is_personal_and_admin_has_global_filters(client, library):
    alice=borrow(client,library)
    bob=borrow(client,library,'bob')
    mine=client.get('/loans/me',headers=library['alice_headers']).json()
    assert [item['id'] for item in mine]==[alice['id']]
    assert client.get('/loans',headers=library['alice_headers']).status_code==403
    assert client.get(f'/loans/{bob["id"]}',headers=library['alice_headers']).status_code==403
    assert client.get(f'/loans/{bob["id"]}',headers=library['admin_headers']).status_code==200
    assert len(client.get('/loans',headers=library['admin_headers']).json())==2
    assert len(client.get(f'/loans?user_id={library["alice"].id}&book_id={library["book"].id}',headers=library['admin_headers']).json())==1
    assert len(client.get('/loans?limit=1&offset=1',headers=library['admin_headers']).json())==1


@pytest.mark.parametrize('status',['DAMAGED','LOST','WITHDRAWN'])
def test_out_of_service_copies_cannot_be_borrowed(client, library, db, status):
    for copy in library['copies']: copy.service_status=status
    db.commit()
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id}).status_code==409
    assert stock(client,library)['is_available'] is False


def test_disabled_book_and_account_are_refused(client, library):
    assert client.delete(f'/books/{library["book"].id}',headers=library['admin_headers']).status_code==200
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id}).status_code==409
    assert client.delete(f'/users/{library["alice"].id}',headers=library['admin_headers']).status_code==200
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id}).status_code==401


def test_invalid_missing_and_unauthenticated_requests(client, library):
    assert client.post('/loans',json={'book_id':library['book'].id}).status_code==401
    assert client.get('/loans/me').status_code==401
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':0}).status_code==422
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id,'user_id':library['bob'].id}).status_code==422
    assert client.post('/loans',headers=library['alice_headers'],json={'book_id':999}).status_code==404
    assert client.get('/loans/999',headers=library['alice_headers']).status_code==404
    assert client.post('/loans/999/return',headers=library['alice_headers']).status_code==404


def test_database_rejects_two_active_loans_for_one_copy(client, library, db):
    loan=borrow(client,library)
    db.add(Loan(user_id=library['bob'].id,copy_id=loan['copy_id'],borrowed_at=utc_now()))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    assert len(db.scalars(select(Loan)).all())==1


def test_failed_borrow_is_rolled_back(client, library, db, monkeypatch):
    def fail_commit():
        db.flush()
        raise IntegrityError('borrow', {}, Exception('simulated failure'))

    monkeypatch.setattr(db, 'commit', fail_commit)
    response=client.post('/loans',headers=library['alice_headers'],json={'book_id':library['book'].id})
    assert response.status_code==409
    assert db.scalars(select(Loan)).all()==[]
    assert stock(client,library)['available_stock']==2


@pytest.mark.parametrize('changes',[
    {'closed_at':utc_now()},
    {'closure_reason':'RETURNED'},
    {'closed_at':utc_now(),'closure_reason':'INVALID','closed_by_id':1},
    {'closed_at':utc_now()-timedelta(days=1),'closure_reason':'RETURNED','closed_by_id':1},
])
def test_database_requires_coherent_closure(library, db, changes):
    loan=Loan(user_id=library['alice'].id,copy_id=library['copies'][0].id,borrowed_at=utc_now(),**changes)
    db.add(loan)
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()


def admin_borrow(client, library, user='alice', expected=201):
    response = client.post('/admin/loans', headers=library['admin_headers'], json={
        'user_id': library[user].id, 'book_id': library['book'].id,
    })
    assert response.status_code == expected
    return response.json()


def admin_close(client, library, loan, status, expected=200):
    response = client.post(f'/admin/loans/{loan["id"]}/close', headers=library['admin_headers'],
                           json={'copy_status': status})
    assert response.status_code == expected
    return response.json()


def test_admin_records_loan_for_borrower(client, library):
    loan = admin_borrow(client, library)
    assert loan['user_id'] == library['alice'].id
    assert client.get('/loans/me', headers=library['alice_headers']).json()[0]['id'] == loan['id']
    assert client.get('/loans/me', headers=library['admin_headers']).json() == []
    assert stock(client, library)['available_stock'] == 1
    admin_borrow(client, library, 'bob')
    admin_borrow(client, library, expected=409)


@pytest.mark.parametrize('status,reason,available', [
    ('IN_SERVICE', 'RETURNED', 2), ('DAMAGED', 'RETURNED', 1), ('LOST', 'LOST', 1),
])
def test_admin_closure_updates_copy_and_history(client, library, db, status, reason, available):
    loan = borrow(client, library)
    result = admin_close(client, library, loan, status)
    assert result['closure_reason'] == reason
    assert result['closed_by_id'] == library['admin'].id
    assert result['closed_at'] >= result['borrowed_at'] and result['is_active'] is False
    assert db.get(BookCopy, loan['copy_id']).service_status == status
    assert stock(client, library)['available_stock'] == available
    assert stock(client, library)['total_stock'] == 2
    admin_close(client, library, loan, 'IN_SERVICE', expected=409)
    assert db.get(BookCopy, loan['copy_id']).service_status == status
    assert client.post(f'/loans/{loan["id"]}/return', headers=library['alice_headers']).status_code == 409
    assert client.get('/loans/me', headers=library['alice_headers']).json()[0]['closure_reason'] == reason


@pytest.mark.parametrize('status', ['DAMAGED', 'LOST'])
def test_repair_or_recovery_allows_new_loan_without_reopening_history(client, library, db, status):
    loan = borrow(client, library)
    admin_close(client, library, loan, status)
    copy_url = f'/books/{library["book"].id}/copies/{loan["copy_id"]}'
    assert client.patch(copy_url, headers=library['admin_headers'], json={'service_status': 'IN_SERVICE'}).status_code == 200
    again = borrow(client, library)
    assert again['copy_id'] == loan['copy_id'] and again['id'] != loan['id']
    assert db.get(Loan, loan['id']).closed_at is not None
    assert db.get(Loan, loan['id']).closure_reason == ('LOST' if status == 'LOST' else 'RETURNED')


def test_admin_respects_blacklist_and_inactive_borrower_but_can_close(client, library, db):
    loan = borrow(client, library)
    assert client.patch(f'/users/{library["alice"].id}/blacklist', headers=library['admin_headers'],
                        json={'is_blacklisted': True}).status_code == 200
    admin_borrow(client, library, expected=403)
    admin_close(client, library, loan, 'DAMAGED')
    # Un compte désactivé par un import ou une intervention en base peut encore avoir un prêt.
    other = borrow(client, library, 'bob')
    library['bob'].is_active = False
    db.commit()
    admin_borrow(client, library, 'bob', expected=409)
    admin_close(client, library, other, 'LOST')


def test_admin_routes_permissions_and_validation(client, library):
    loan = borrow(client, library)
    payload = {'book_id': library['book'].id, 'user_id': library['bob'].id}
    url = f'/admin/loans/{loan["id"]}/close'
    assert client.post('/admin/loans', json=payload).status_code == 401
    assert client.post(url, json={'copy_status': 'LOST'}).status_code == 401
    assert client.post('/admin/loans', headers=library['alice_headers'], json=payload).status_code == 403
    assert client.post(url, headers=library['alice_headers'], json={'copy_status': 'LOST'}).status_code == 403
    assert client.post('/admin/loans', headers=library['admin_headers'], json={**payload, 'user_id': 999}).status_code == 404
    assert client.post('/admin/loans', headers=library['admin_headers'], json={**payload, 'user_id': 0}).status_code == 422
    assert client.post('/admin/loans', headers=library['admin_headers'], json={**payload, 'book_id': 999}).status_code == 404
    assert client.post('/admin/loans/999/close', headers=library['admin_headers'], json={'copy_status': 'LOST'}).status_code == 404
    for invalid in [{}, {'copy_status': 'WITHDRAWN'}, {'copy_status': 'LOST', 'closed_by_id': 999}]:
        assert client.post(url, headers=library['admin_headers'], json=invalid).status_code == 422
    assert stock(client, library)['available_stock'] == 1


def test_admin_cannot_borrow_disabled_book(client, library):
    assert client.delete(f'/books/{library["book"].id}', headers=library['admin_headers']).status_code == 200
    admin_borrow(client, library, expected=409)


@pytest.mark.parametrize('status', ['DAMAGED', 'LOST'])
def test_failed_admin_closure_rolls_back_loan_and_copy(client, library, db, monkeypatch, status):
    loan = borrow(client, library)
    def fail_commit():
        db.flush()
        raise IntegrityError('close', {}, Exception('simulated failure'))
    monkeypatch.setattr(db, 'commit', fail_commit)
    admin_close(client, library, loan, status, expected=409)
    assert db.get(Loan, loan['id']).closed_at is None
    assert db.get(Loan, loan['id']).closed_by_id is None
    assert db.get(BookCopy, loan['copy_id']).service_status == 'IN_SERVICE'
    assert stock(client, library)['available_stock'] == 1
