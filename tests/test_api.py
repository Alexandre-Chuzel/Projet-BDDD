import dotenv
from fastapi.testclient import TestClient
from main import app
import pytest
import os, time

dotenv.load_dotenv()

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200

def test_get_user():
    response = client.get("/user/1")
    assert response.status_code == 200
    assert response.json() == {"name": "Alice", "age": 30}

def test_post_user():
    response = client.post("/user/1", json={"name": "Bob", "age": 25})
    assert response.status_code == 200
    assert response.json() == {"name": "Bob", "age": 25}