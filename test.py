"""Vérification manuelle d'un compte existant sur une API déjà démarrée."""
from getpass import getpass

import httpx


def main():
    email = input('Email : ').strip()
    secret = getpass('Mot de passe : ')
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=10) as client:
        response = client.post('/login', data={'username': email, 'password': secret})
        response.raise_for_status()
        headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
        response = client.get('/private', headers=headers)
        response.raise_for_status()
        print(response.json()['message'])


if __name__ == '__main__':
    main()
