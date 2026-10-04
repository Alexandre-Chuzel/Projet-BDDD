from datetime import datetime, timedelta, timezone
import os

import jwt
import pytest

from models import User
from security import password


def signup(client, email='alice@example.com'):
    response = client.post('/users', json={
        'name': 'Alice', 'email': email, 'password': 'secret-password',
    })
    assert response.status_code == 201
    return response.json()


def login(client, email='alice@example.com', password_value='secret-password'):
    return client.post('/login', data={'username': email, 'password': password_value})


def authorization(client):
    response = login(client)
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_root_and_documentation(client):
    assert client.get('/').status_code == 200
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').status_code == 200


def test_startup_does_not_create_tables_in_configured_database(client):
    from database import engine
    from sqlalchemy import inspect

    assert inspect(engine).get_table_names() == []


def test_unrecognized_password_hash_is_rejected(client, db):
    db.add(User(name='Legacy', email='legacy@example.com', password='unrecognized-hash'))
    db.commit()
    assert login(client, 'legacy@example.com').status_code == 401


def test_signup_hashes_password_and_normalizes_email(client, db):
    user = signup(client, 'ALICE@example.com')
    assert user['email'] == 'alice@example.com'
    assert 'password' not in user
    stored = db.get(User, user['id'])
    assert stored.password != 'secret-password'
    assert password.verify('secret-password', stored.password)


def test_duplicate_email_is_conflict(client):
    signup(client)
    response = client.post('/users', json={
        'name': 'Autre', 'email': 'ALICE@example.com', 'password': 'other-password',
    })
    assert response.status_code == 409


@pytest.mark.parametrize('changes', [
    {'name': '   '}, {'email': 'invalide'}, {'password': 'short'}, {'role': 'ADMIN'},
])
def test_invalid_signup(client, changes):
    data = {'name': 'Alice', 'email': 'alice@example.com', 'password': 'secret-password'}
    data.update(changes)
    assert client.post('/users', json=data).status_code == 422


def test_login_and_private_route(client):
    user = signup(client)
    response = login(client, 'ALICE@example.com')
    assert response.status_code == 200
    token = response.json()['access_token']
    payload = jwt.decode(token, os.environ['SECRET_KEY'], algorithms=['HS256'])
    assert payload['sub'] == str(user['id'])
    assert 'exp' in payload
    assert client.get('/private', headers={'Authorization': 'Bearer ' + token}).json() == {
        'message': 'Bonjour Alice',
    }


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


def test_cannot_read_update_or_delete_another_account(client):
    signup(client)
    other = signup(client, 'bob@example.com')
    headers = authorization(client)
    url = f"/users/{other['id']}"
    assert client.get(url, headers=headers).status_code == 403
    assert client.put(url, headers=headers, json={
        'name': 'Hacked', 'email': 'hack@example.com', 'password': 'hacked-password',
    }).status_code == 403
    assert client.delete(url, headers=headers).status_code == 403
    assert client.get('/users', headers=headers).status_code == 405


def test_update_changes_password_and_keeps_identity_token(client):
    user = signup(client)
    headers = authorization(client)
    response = client.put(f"/users/{user['id']}", headers=headers, json={
        'name': 'Alice Modifiée', 'email': 'new@example.com', 'password': 'new-password',
    })
    assert response.status_code == 200
    assert 'password' not in response.json()
    assert login(client).status_code == 401
    assert login(client, 'new@example.com').status_code == 401
    assert login(client, 'new@example.com', 'new-password').status_code == 200
    assert client.get('/private', headers=headers).status_code == 200


def test_duplicate_update_does_not_change_account(client):
    user = signup(client)
    signup(client, 'bob@example.com')
    headers = authorization(client)
    assert client.put(f"/users/{user['id']}", headers=headers, json={
        'name': 'Changed', 'email': 'bob@example.com', 'password': 'new-password',
    }).status_code == 409
    assert login(client).status_code == 200


def test_deleted_account_token_is_rejected(client):
    user = signup(client)
    headers = authorization(client)
    assert client.delete(f"/users/{user['id']}", headers=headers).status_code == 200
    assert client.get('/private', headers=headers).status_code == 401
