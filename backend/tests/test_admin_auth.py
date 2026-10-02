import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-admin-auth-tests-32")
    monkeypatch.setenv("ADMIN_EMAILS", "ADMIN@example.com")

    from app.db import Base, get_db
    from app.main import app

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_get_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _register(client, email):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_admin_authentication_and_login_events(client):
    regular_token = _register(client, "user@example.com")
    admin_token = _register(client, "admin@example.com")
    regular_headers = {"Authorization": f"Bearer {regular_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    assert client.get("/admin/users", headers=regular_headers).status_code == 403
    users_response = client.get("/admin/users", headers=admin_headers)
    assert users_response.status_code == 200
    assert {user["email"] for user in users_response.json()} == {
        "user@example.com",
        "admin@example.com",
    }
    assert all(
        "password_hash" not in user and "document_count" in user
        for user in users_response.json()
    )
    assert (
        client.get("/auth/me", headers=admin_headers).json()["is_admin"]
        is True
    )
    admin_login = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert admin_login.status_code == 200
    assert any(
        user["email"] == "admin@example.com" and user["last_login_at"]
        for user in client.get("/admin/users", headers=admin_headers).json()
    )

    failed_login = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "incorrect"},
    )
    assert failed_login.status_code == 401

    regular_user = next(
        user for user in users_response.json()
        if user["email"] == "user@example.com"
    )
    disabled_response = client.patch(
        f"/admin/users/{regular_user['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert disabled_response.status_code == 200
    assert disabled_response.json()["is_active"] is False
    assert client.get("/documents", headers=regular_headers).status_code == 401

    disabled_login = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    unknown_login = client.post(
        "/auth/login",
        json={"email": "unknown@example.com", "password": "password123"},
    )
    assert disabled_login.status_code == 401
    assert disabled_login.json()["detail"] == unknown_login.json()["detail"]

    events_response = client.get("/admin/login-events", headers=admin_headers)
    assert events_response.status_code == 200
    events = events_response.json()
    assert any(
        event["email"] == "user@example.com" and event["success"] is False
        for event in events
    )
    assert any(
        event["email"] == "unknown@example.com" and event["success"] is False
        for event in events
    )
    assert any(
        event["email"] == "admin@example.com" and event["success"] is True
        for event in events
    )
    assert all("token" not in event and "password" not in event for event in events)
