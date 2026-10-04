import pytest

from models import Book, BookCopy, User
from security import password


@pytest.fixture
def access(client, db):
    admin = User(first_name='Admin', last_name='Test', email='admin@example.com',
                 password_hash=password.hash('secret-password'), role='ADMIN')
    user = User(first_name='User', last_name='Test', email='user@example.com',
                password_hash=password.hash('secret-password'))
    db.add_all([admin, user])
    db.commit()
    def headers(email):
        response = client.post('/login', data={'username': email, 'password': 'secret-password'})
        assert response.status_code == 200
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    return headers(admin.email), headers(user.email)


def author(client, headers, first_name='Victor', last_name='Hugo'):
    response = client.post('/authors', headers=headers, json={'first_name': first_name, 'last_name': last_name})
    assert response.status_code == 201
    return response.json()['id']


def book_data(author_ids, **changes):
    return {'title': 'Les Misérables', 'genre': 'Roman', 'author_ids': author_ids, **changes}


def book(client, headers, **changes):
    author_id = author(client, headers)
    response = client.post('/books', headers=headers, json=book_data([author_id], **changes))
    assert response.status_code == 201
    return response.json()


def copy(client, headers, book_id, code, status='IN_SERVICE'):
    response = client.post(f'/books/{book_id}/copies', headers=headers, json={
        'inventory_code': code, 'service_status': status,
    })
    assert response.status_code == 201
    return response.json()


def test_catalogue_requires_authentication(client):
    for url in ('/authors', '/books', '/authors/1', '/books/1'):
        assert client.get(url).status_code == 401


def test_user_can_read_but_cannot_manage_catalogue_or_see_copies(client, access):
    admin, user = access
    data = book(client, admin)
    book_id = data['id']
    assert client.get('/authors', headers=user).status_code == 200
    assert client.get(f'/authors/{data["authors"][0]["id"]}', headers=user).status_code == 200
    assert client.post('/authors', headers=user, json={'first_name': 'X', 'last_name': 'Y'}).status_code == 403
    assert client.post('/books', headers=user, json=book_data([data['authors'][0]['id']])).status_code == 403
    assert client.put(f'/books/{book_id}', headers=user, json=book_data([data['authors'][0]['id']])).status_code == 403
    assert client.delete(f'/books/{book_id}', headers=user).status_code == 403
    assert client.get(f'/books/{book_id}/copies', headers=user).status_code == 403
    assert client.post(f'/books/{book_id}/copies', headers=user, json={'inventory_code': 'EX-1'}).status_code == 403
    assert client.get('/books?include_inactive=true', headers=user).status_code == 403


def test_multiple_authors_and_no_copy_means_unavailable(client, access):
    admin, user = access
    authors = [author(client, admin), author(client, admin, 'Émile', 'Zola')]
    response = client.post('/books', headers=admin, json=book_data(authors, publication_date='1862-01-01'))
    assert response.status_code == 201
    data = response.json()
    assert len(data['authors']) == 2
    assert data['publication_date'] == '1862-01-01'
    assert data['total_stock'] == data['available_stock'] == 0
    assert data['is_available'] is False
    public = client.get(f'/books/{data["id"]}', headers=user).json()
    assert 'total_stock' not in public and 'available_stock' not in public


def test_stock_counts_service_damaged_lost_and_withdrawn(client, access):
    admin, user = access
    data = book(client, admin)
    book_id = data['id']
    first = copy(client, admin, book_id, ' ex-001 ')
    copy(client, admin, book_id, 'EX-002', 'DAMAGED')
    copy(client, admin, book_id, 'EX-003', 'LOST')
    withdrawn = copy(client, admin, book_id, 'EX-004', 'WITHDRAWN')
    assert first['inventory_code'] == 'EX-001'
    view = client.get(f'/books/{book_id}', headers=admin).json()
    assert view['total_stock'] == 3 and view['available_stock'] == 1 and view['is_available'] is True
    public = client.get('/books', headers=user).json()[0]
    assert public['is_available'] is True and 'total_stock' not in public and 'available_stock' not in public
    assert len(client.get(f'/books/{book_id}/copies', headers=admin).json()) == 4
    assert client.delete(f'/books/{book_id}/copies/{first["id"]}', headers=admin).json()['service_status'] == 'WITHDRAWN'
    view = client.get(f'/books/{book_id}', headers=admin).json()
    assert view['total_stock'] == 2 and view['available_stock'] == 0 and view['is_available'] is False
    assert client.patch(f'/books/{book_id}/copies/{withdrawn["id"]}', headers=admin, json={'service_status': 'IN_SERVICE'}).status_code == 200
    assert client.get(f'/books/{book_id}', headers=admin).json()['available_stock'] == 1


def test_inventory_code_is_unique_even_after_withdrawal(client, access):
    admin, _ = access
    data = book(client, admin)
    first = copy(client, admin, data['id'], 'EX-001')
    client.delete(f'/books/{data["id"]}/copies/{first["id"]}', headers=admin)
    another = book(client, admin, title='Autre livre')
    response = client.post(f'/books/{another["id"]}/copies', headers=admin, json={'inventory_code': 'ex-001'})
    assert response.status_code == 409
    assert client.get('/books', headers=admin).status_code == 200


def test_copy_cannot_be_updated_using_another_book_id(client, access):
    admin, _ = access
    first = book(client, admin)
    another = book(client, admin, title='Autre livre')
    item = copy(client, admin, first['id'], 'EX-001')
    for method in ('patch', 'delete'):
        kwargs = {'json': {'service_status': 'DAMAGED'}} if method == 'patch' else {}
        assert getattr(client, method)(f'/books/{another["id"]}/copies/{item["id"]}', headers=admin, **kwargs).status_code == 404
    assert client.get(f'/books/{first["id"]}', headers=admin).json()['available_stock'] == 1


def test_search_title_author_genre_combined_and_pagination(client, access):
    admin, user = access
    book(client, admin)
    book(client, admin, title='Autre titre', genre='Essai')
    for query in ('title=MIS', 'author=victor hugo', 'genre=ROMAN', 'title=mis&author=hugo&genre=roman'):
        result = client.get('/books?' + query, headers=user)
        assert result.status_code == 200
        assert any(item['title'] == 'Les Misérables' for item in result.json())
    assert client.get('/books?genre=roman&title=autre', headers=user).json() == []
    assert client.get('/books?title=%25', headers=user).json() == []
    assert len(client.get('/books?limit=1&offset=1', headers=user).json()) == 1
    assert len(client.get('/authors?name=HUGO&limit=1', headers=user).json()) == 1


def test_isbn10_and_isbn13_cannot_duplicate_an_edition(client, access):
    admin, _ = access
    first = book(client, admin, isbn='0-306-40615-2')
    assert first['isbn'] == '9780306406157'
    author_id = first['authors'][0]['id']
    response = client.post('/books', headers=admin, json=book_data([author_id], isbn='978-0-306-40615-7'))
    assert response.status_code == 409
    assert client.get(f'/books/{first["id"]}', headers=admin).status_code == 200


@pytest.mark.parametrize('changes', [
    {'title': '   '}, {'genre': ''}, {'author_ids': []}, {'author_ids': [-1]},
    {'author_ids': [1, 1]}, {'isbn': '9780306406158'}, {'isbn': 'invalid'},
    {'publication_date': 'invalid'}, {'total_stock': 3},
])
def test_invalid_book_input(client, access, changes):
    admin, _ = access
    author_id = author(client, admin)
    data = book_data([author_id])
    data.update(changes)
    assert client.post('/books', headers=admin, json=data).status_code == 422


def test_missing_author_refused_and_last_author_cannot_be_removed(client, access):
    admin, _ = access
    assert client.post('/books', headers=admin, json=book_data([999])).status_code == 404
    data = book(client, admin)
    assert client.put(f'/books/{data["id"]}', headers=admin, json=book_data([])).status_code == 422
    assert client.delete(f'/authors/{data["authors"][0]["id"]}', headers=admin).status_code == 409


def test_book_update_replaces_author_list_and_author_management(client, access):
    admin, _ = access
    data = book(client, admin)
    second = author(client, admin, 'Émile', 'Zola')
    update = client.put(f'/books/{data["id"]}', headers=admin, json=book_data([second], title='Germinal'))
    assert update.status_code == 200
    assert [item['id'] for item in update.json()['authors']] == [second]
    assert client.delete(f'/authors/{data["authors"][0]["id"]}', headers=admin).status_code == 200
    assert client.put(f'/authors/{second}', headers=admin, json={'first_name': 'Emile', 'last_name': 'Zola'}).status_code == 200
    assert client.get(f'/books/{data["id"]}', headers=admin).json()['authors'][0]['first_name'] == 'Emile'


def test_book_soft_delete_and_restore_preserve_copies_and_isbn(client, access, db):
    admin, user = access
    data = book(client, admin, isbn='9780306406157')
    item = copy(client, admin, data['id'], 'EX-001')
    assert client.delete(f'/books/{data["id"]}', headers=admin).status_code == 200
    assert db.get(Book, data['id']).is_active is False
    assert db.get(BookCopy, item['id']) is not None
    assert client.get(f'/books/{data["id"]}', headers=user).status_code == 404
    assert client.get('/books', headers=user).json() == []
    assert client.get(f'/books/{data["id"]}', headers=admin).json()['is_available'] is False
    assert len(client.get('/books?include_inactive=true', headers=admin).json()) == 1
    assert client.post(f'/books/{data["id"]}/copies', headers=admin, json={'inventory_code': 'EX-002'}).status_code == 409
    assert client.post(f'/books/{data["id"]}/restore', headers=admin).json()['is_available'] is True


def test_unknown_resources_and_invalid_copy_status(client, access):
    admin, _ = access
    assert client.get('/books/999', headers=admin).status_code == 404
    assert client.get('/authors/999', headers=admin).status_code == 404
    assert client.get('/books/999/copies', headers=admin).status_code == 404
    data = book(client, admin)
    assert client.post(f'/books/{data["id"]}/copies', headers=admin, json={'inventory_code': '  '}).status_code == 422
    assert client.post(f'/books/{data["id"]}/copies', headers=admin, json={'inventory_code': 'EX-1', 'service_status': 'INVALID'}).status_code == 422
