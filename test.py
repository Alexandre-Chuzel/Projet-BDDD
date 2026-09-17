import httpx

BASE_URL = "http://127.0.0.1:8000"


# 1. CREER UN UTILISATEUR
print("\n--- POST /users ---")

response = httpx.post(
    f"{BASE_URL}/users",
    json={
        "name": "alice",
        "email": "alice@test.fr",
        "password": "testpassword"
    }
)

print(response.status_code)
print(response.json())


# 2. LOGIN
print("\n--- POST /login ---")

response = httpx.post(
    f"{BASE_URL}/login",
    data={
        "username": "alice",
        "password": "testpassword"
    }
)

print(response.status_code)
print(response.json())

token = response.json()["access_token"]


# 3. ROUTE PRIVEE
print("\n--- GET /private ---")

headers = {
    "Authorization": f"Bearer {token}"
}

response = httpx.get(
    f"{BASE_URL}/private",
    headers=headers
)

print(response.status_code)
print(response.json())


# 4. LISTE DES UTILISATEURS
print("\n--- GET /users ---")

response = httpx.get(
    f"{BASE_URL}/users",
    headers=headers
)

print(response.status_code)
print(response.json())


# 5. RECUPERER UN USER
print("\n--- GET /users/1 ---")

response = httpx.get(
    f"{BASE_URL}/users/1",
    headers=headers
)

print(response.status_code)
print(response.json())


# 6. MODIFIER UN USER
print("\n--- PUT /users/1 ---")

response = httpx.put(
    f"{BASE_URL}/users/1",
    headers=headers,
    json={
        "name": "alice_modifiee",
        "email": "alice2@test.fr",
        "password": "testpassword"
    }
)

print(response.status_code)
print(response.json())


# 7. SUPPRIMER UN USER
print("\n--- DELETE /users/1 ---")

response = httpx.delete(
    f"{BASE_URL}/users/1",
    headers=headers
)

print(response.status_code)
print(response.json())