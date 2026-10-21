from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification():
    plain_password = "SecurePassword123!"
    hashed = hash_password(plain_password)

    # Must be hashed, not plaintext
    assert hashed != plain_password
    assert "$argon2" in hashed

    # Valid password verification
    assert verify_password(plain_password, hashed) is True

    # Invalid password verification
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_jwt_create_and_decode():
    user_id = uuid4()
    token = create_access_token(user_id)

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert "exp" in payload


def test_jwt_custom_expiration():
    user_id = uuid4()
    token = create_access_token(user_id, expires_delta=timedelta(minutes=5))

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)


def test_jwt_expired_token():
    user_id = uuid4()
    # Create an expired token by setting negative timedelta
    expired_token = create_access_token(user_id, expires_delta=timedelta(seconds=-10))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)


def test_jwt_invalid_token():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not.a.valid.jwt.token")

    # Valid format, wrong signature
    tampered_token = jwt.encode(
        {"sub": str(uuid4())},
        "wrong_secret_key_12345678901234567890",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(tampered_token)
