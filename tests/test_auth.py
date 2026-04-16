from __future__ import annotations

import pytest

from aistation.auth import build_login_payload, sm2_encrypt_password
from aistation.errors import AuthError


def test_sm2_encrypt_password_uses_mode_zero_and_readds_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeSM2:
        def __init__(self, *, public_key: str, private_key: str, mode: int) -> None:
            calls["public_key"] = public_key
            calls["private_key"] = private_key
            calls["mode"] = mode

        def encrypt(self, data: bytes) -> bytes:
            calls["data"] = data
            return b"\xaa\xbb\xcc"

    monkeypatch.setattr("aistation.auth.CryptSM2", FakeSM2)

    result = sm2_encrypt_password("secret", "04" + "11" * 64)

    assert calls == {
        "public_key": "11" * 64,
        "private_key": "",
        "mode": 0,
        "data": b"secret",
    }
    assert result == "04aabbcc"


def test_sm2_encrypt_password_validates_public_key_length() -> None:
    with pytest.raises(AuthError, match="Invalid SM2 public key length"):
        sm2_encrypt_password("secret", "abcd")


def test_sm2_encrypt_password_raises_when_gmssl_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSM2:
        def __init__(self, *, public_key: str, private_key: str, mode: int) -> None:
            del public_key, private_key, mode

        def encrypt(self, data: bytes) -> None:
            del data
            return None

    monkeypatch.setattr("aistation.auth.CryptSM2", FakeSM2)

    with pytest.raises(AuthError, match="gmssl returned None"):
        sm2_encrypt_password("secret", "04" + "11" * 64)


def test_build_login_payload_adds_optional_captcha() -> None:
    assert build_login_payload("alice", "cipher") == {"account": "alice", "password": "cipher"}
    assert build_login_payload("alice", "cipher", "1234") == {
        "account": "alice",
        "password": "cipher",
        "captcha": "1234",
    }
