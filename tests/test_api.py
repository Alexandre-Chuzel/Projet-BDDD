from datetime import datetime, timedelta, timezone
import os

import jwt
import pytest

from models import User
from security import password


def identity(email='alice@example.com'):
    return {'first_name': 'Alice', 'last_name': 'Martin', 'email': email}


def signup(client, email='alice@example.com'):
    response = client.post('/users', json={**identity(email), 'password': 'secret-password'})
    assert response.status_code == 201
    return response.json()


def login(client, email='alice@example.com', password_value='secret-password'):
    return client.post('/login', data={'username': email, 'password': password_value})


def authorization(client, email='alice@example.com'):
    response = login(client, email)
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


@pytest.fixture
def admin(client, db):
    user = User(first_name='Admin', last_name='Martin', email='admin@example.com',
                password_hash=password.hash('secret-password'), role='ADMIN')
    db.add(user)
    db.commit()
    return user, authorization(client, user.email)


def test_root_and_documentation(client):
    assert client.get('/').status_code == 200
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').status_code == 200


def test_startup_does_not_create_tables_in_configured_database(client):
    from database import engine
    from sqlalchemy import inspect
    assert inspect(engine).get_table_names() == []


def test_unrecognized_password_hash_is_rejected(client, db):
    db.add(User(first_name='Legacy', email='legacy@example.com', password_hash='unrecognized-hash'))
    db.commit()
    assert login(client, 'legacy@example.com').status_code == 401


def test_signup_hashes_password_normalizes_email_and_sets_defaults(client, db):
    user = signup(client, 'ALICE@example.com')
    assert user['email'] == 'alice@example.com'
    assert 'password' not in user and 'password_hash' not in user
    assert user['role'] == 'USER'
    assert user['is_active'] is True and user['is_blacklisted'] is False
    stored = db.get(User, user['id'])
    assert stored.password_hash != 'secret-password'
    assert password.verify('secret-password', stored.password_hash)


def test_duplicate_email_is_conflict(client):
    signup(client)
    assert client.post('/users', json={**identity('ALICE@example.com'), 'password': 'other-password'}).status_code == 409


@pytest.mark.parametrize('changes', [
    {'first_name': '   '}, {'last_name': ''}, {'email': 'invalide'},
    {'password': 'short'}, {'role': 'ADMIN'}, {'is_active': False},
    {'is_blacklisted': True}, {'phone': 'not-a-number'},
])
def test_invalid_signup(client, changes):
    data = {**identity(), 'password': 'secret-password'}
    data.update(changes)
    assert client.post('/users', json=data).status_code == 422


def test_login_and_private_route(client):
    user = signup(client)
    response = login(client, 'ALICE@example.com')
    assert response.status_code == 200
    token = response.json()['access_token']
    payload = jwt.decode(token, os.environ['SECRET_KEY'], algorithms=['HS256'])
    assert payload['sub'] == str(user['id']) and 'exp' in payload
    assert client.get('/private', headers={'Authorization': 'Bearer ' + token}).json() == {'message': 'Bonjour Alice'}


def test_login_errors_do_not_disclose_account_existence(client):
    signup(client)
    wrong = login(client, password_value='wrong-password')
    absent = login(client, 'absent@example.com')
    assert wrong.status_code == absent.status_code == 401
    assert wrong.json() == absent.json()
    assert wrong.headers['www-authenticate'] == 'Bearer'


def test_missing_authentication(client):
    signup(client)
    for method in ('get', 'put', 'delete'):
        assert getattr(client, method)('/users/1').status_code == 401
    assert client.get('/users/me').status_code == 401
    assert client.get('/private').status_code == 401


@pytest.mark.parametrize('payload', [
    {'sub': '1', 'exp': datetime.now(timezone.utc) - timedelta(minutes=1)},
    {'sub': '1'},
    {'sub': 'unknown', 'exp': datetime.now(timezone.utc) + timedelta(minutes=1)},
    {'sub': '999', 'exp': datetime.now(timezone.utc) + timedelta(minutes=1)},
])
def test_invalid_expired_or_unknown_user_token(client, payload):
    signup(client)
    token = jwt.encode(payload, os.environ['SECRET_KEY'], algorithm='HS256')
    response = client.get('/private', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer'


def test_wrong_signature(client):
    signup(client)
    token = jwt.encode({'sub': '1', 'exp': datetime.now(timezone.utc) + timedelta(minutes=1)},
                       'another-test-secret-at-least-32-bytes', algorithm='HS256')
    assert client.get('/private', headers={'Authorization': 'Bearer ' + token}).status_code == 401


def test_normal_user_can_read_only_own_account_and_cannot_manage_users(client):
    user = signup(client)
    other = signup(client, 'bob@example.com')
    headers = authorization(client)
    assert client.get('/users/me', headers=headers).json()['id'] == user['id']
    assert client.get(f"/users/{user['id']}", headers=headers).status_code == 200
    assert client.get(f"/users/{other['id']}", headers=headers).status_code == 403
    assert client.get('/users', headers=headers).status_code == 403
    assert client.put(f"/users/{user['id']}", headers=headers, json=identity()).status_code == 403
    assert client.delete(f"/users/{user['id']}", headers=headers).status_code == 403
    assert client.patch(f"/users/{other['id']}/blacklist", headers=headers, json={'is_blacklisted': True}).status_code == 403
    assert client.post(f"/users/{other['id']}/restore", headers=headers).status_code == 403
    assert client.post('/admin/users', headers=headers, json={**identity('new@example.com'), 'password': 'secret-password', 'role': 'ADMIN'}).status_code == 403


def test_admin_can_create_admin_and_list_accounts(client, admin):
    _, headers = admin
    user = signup(client)
    response = client.post('/admin/users', headers=headers, json={
        **identity('secondadmin@example.com'), 'password': 'secret-password', 'role': 'ADMIN',
    })
    assert response.status_code == 201 and response.json()['role'] == 'ADMIN'
    assert client.get(f"/users/{user['id']}", headers=headers).status_code == 200
    users = client.get('/users', headers=headers).json()
    assert len(users) == 3
    assert all('password_hash' not in account for account in users)
    assert len(client.get('/users?limit=1&offset=1', headers=headers).json()) == 1


def test_admin_update_can_keep_or_change_password(client, admin):
    _, headers = admin
    user = signup(client)
    assert client.put(f"/users/{user['id']}", headers=headers, json=identity()).status_code == 200
    assert login(client).status_code == 200
    response = client.put(f"/users/{user['id']}", headers=headers, json={
        **identity('new@example.com'), 'password': 'new-password', 'phone': '+33 6 12 34 56 78',
    })
    assert response.status_code == 200 and response.json()['phone'] == '+33 6 12 34 56 78'
    assert login(client).status_code == 401
    assert login(client, 'new@example.com').status_code == 401
    assert login(client, 'new@example.com', 'new-password').status_code == 200


def test_duplicate_update_does_not_change_account(client, admin):
    _, headers = admin
    user = signup(client)
    signup(client, 'bob@example.com')
    assert client.put(f"/users/{user['id']}", headers=headers, json=identity('bob@example.com')).status_code == 409
    assert login(client).status_code == 200


def test_blacklist_allows_login_and_private_access(client, admin):
    _, headers = admin
    user = signup(client)
    user_headers = authorization(client)
    url = f"/users/{user['id']}/blacklist"
    response = client.patch(url, headers=headers, json={'is_blacklisted': True})
    assert response.status_code == 200 and response.json()['is_blacklisted'] is True
    assert login(client).status_code == 200
    assert client.get('/private', headers=user_headers).status_code == 200
    assert client.patch(url, headers=headers, json={'is_blacklisted': False}).json()['is_blacklisted'] is False


def test_soft_delete_rejects_login_and_token_and_preserves_account(client, db, admin):
    _, headers = admin
    user = signup(client)
    user_headers = authorization(client)
    assert client.delete(f"/users/{user['id']}", headers=headers).status_code == 200
    assert db.get(User, user['id']).is_active is False
    assert login(client).status_code == 401
    assert client.get('/private', headers=user_headers).status_code == 401
    assert len(client.get('/users', headers=headers).json()) == 1
    assert len(client.get('/users?include_inactive=true', headers=headers).json()) == 2
    assert client.post('/users', json={**identity(), 'password': 'secret-password'}).status_code == 409
    assert client.post(f"/users/{user['id']}/restore", headers=headers).status_code == 200
    assert login(client).status_code == 200


def test_last_admin_cannot_be_deleted_or_demoted(client, admin):
    user, headers = admin
    assert client.delete(f'/users/{user.id}', headers=headers).status_code == 409
    assert client.put(f'/users/{user.id}', headers=headers, json={
        **identity(user.email), 'role': 'USER',
    }).status_code == 409
    assert client.get('/users', headers=headers).status_code == 200


def test_demoted_admin_token_loses_admin_permissions(client, admin):
    user, headers = admin
    response = client.post('/admin/users', headers=headers, json={
        **identity('second@example.com'), 'password': 'secret-password', 'role': 'ADMIN',
    })
    assert response.status_code == 201
    assert client.put(f'/users/{user.id}', headers=headers, json={
        **identity(user.email), 'role': 'USER',
    }).status_code == 200
    assert client.get('/users', headers=headers).status_code == 403
    assert client.get('/private', headers=headers).status_code == 200


def test_unknown_account_is_not_found_for_admin(client, admin):
    _, headers = admin
    assert client.get('/users/999', headers=headers).status_code == 404
    assert client.delete('/users/999', headers=headers).status_code == 404
    assert client.patch('/users/999/blacklist', headers=headers, json={'is_blacklisted': True}).status_code == 404
