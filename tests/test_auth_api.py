from datetime import timedelta
from uuid import UUID, uuid4

from app.core.security import create_access_token


def test_register_developer_user_success(test_client):
    email = f"user_{uuid4().hex[:8]}@example.com"
    response = test_client.post(
        "/api/auth/register",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["role"] == "developer"
    assert UUID(data["id"])  # Valid UUID


def test_register_administrator_user_success(test_client):
    email = f"admin_{uuid4().hex[:8]}@example.com"
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "role": "administrator",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["role"] == "administrator"


def test_register_with_uppercase_role(test_client):
    email = f"user_upper_{uuid4().hex[:8]}@example.com"
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "role": "DEVELOPER",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["role"] == "developer"


def test_register_duplicate_email(test_client):
    email = f"dup_{uuid4().hex[:8]}@example.com"
    first_res = test_client.post(
        "/api/auth/register",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert first_res.status_code == 201

    second_res = test_client.post(
        "/api/auth/register",
        json={"email": email, "password": "AnotherPassword123!"},
    )
    assert second_res.status_code == 409
    assert second_res.json()["detail"] == "Email is already registered"


def test_register_validation_short_password(test_client):
    response = test_client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_register_validation_invalid_email(test_client):
    response = test_client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "SecurePassword123!"},
    )
    assert response.status_code == 422


def test_login_success(test_client):
    email = f"login_{uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"

    reg_res = test_client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_res.status_code == 201

    login_res = test_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"


def test_login_wrong_password(test_client):
    email = f"wrongpwd_{uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"

    reg_res = test_client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_res.status_code == 201

    login_res = test_client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert login_res.status_code == 401
    assert login_res.json()["detail"] == "Invalid email or password"


def test_login_unregistered_email(test_client):
    login_res = test_client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "AnyPassword123!"},
    )
    assert login_res.status_code == 401
    assert login_res.json()["detail"] == "Invalid email or password"


def test_protected_route_me_with_valid_token(test_client):
    email = f"me_{uuid4().hex[:8]}@example.com"
    password = "Password123!"

    reg_res = test_client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    login_res = test_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    token = login_res.json()["access_token"]

    me_res = test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["id"] == user_id
    assert data["email"] == email
    assert data["role"] == "developer"


def test_protected_route_me_without_token(test_client):
    response = test_client.get("/api/auth/me")
    assert response.status_code == 401


def test_protected_route_me_with_invalid_token(test_client):
    response = test_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid.token.payload"},
    )
    assert response.status_code == 401


def test_protected_route_me_with_expired_token(test_client):
    fake_user_id = uuid4()
    expired_token = create_access_token(
        fake_user_id,
        expires_delta=timedelta(seconds=-10),
    )
    response = test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
