import sys

import pytest

import create_admin
from models import User


def test_first_admin_keeps_password_and_cannot_be_created_twice(db, monkeypatch):
    user = User(first_name='Alice', email='alice@example.com', password_hash='existing-hash')
    db.add(user)
    db.commit()
    user_id = user.id
    monkeypatch.setattr(create_admin, 'SessionLocal', lambda: db)
    monkeypatch.setattr(sys, 'argv', ['create_admin.py', 'ALICE@example.com'])
    create_admin.main()
    user = db.get(User, user_id)
    assert user.role == 'ADMIN'
    assert user.password_hash == 'existing-hash'
    with pytest.raises(SystemExit) as error:
        create_admin.main()
    assert error.value.code == 2


def test_first_admin_requires_an_active_registered_account(db, monkeypatch):
    db.add(User(first_name='Inactive', email='inactive@example.com',
                password_hash='existing-hash', is_active=False))
    db.commit()
    monkeypatch.setattr(create_admin, 'SessionLocal', lambda: db)
    monkeypatch.setattr(sys, 'argv', ['create_admin.py', 'inactive@example.com'])
    with pytest.raises(SystemExit) as error:
        create_admin.main()
    assert error.value.code == 2
