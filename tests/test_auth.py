import pytest
from fastapi import HTTPException

from app.auth import authenticate, create_access_token, decode_token, require_auth


def test_authenticate():
    assert authenticate("guardian", "test-api-password") is True
    assert authenticate("guardian", "wrong") is False
    assert authenticate("attacker", "test-api-password") is False


def test_token_round_trip():
    token = create_access_token("guardian")
    payload = decode_token(token)
    assert payload["sub"] == "guardian"
    assert require_auth(token=token) == "guardian"


def test_require_auth_rejects_garbage():
    with pytest.raises(HTTPException) as exc:
        require_auth(token="not-a-jwt")
    assert exc.value.status_code == 401
