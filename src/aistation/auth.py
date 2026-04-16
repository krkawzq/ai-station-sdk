from __future__ import annotations

from typing import cast

from gmssl.sm2 import CryptSM2  # type: ignore[import-untyped]

from .errors import AuthError


def sm2_encrypt_password(password: str, server_public_key_hex: str) -> str:
    """
    Encrypt a plaintext password for the /login endpoint.

    The AI Station server expects:
    - public key without the leading "04"
    - gmssl mode=0
    - ciphertext hex with "04" prepended back
    """
    public_key = server_public_key_hex.strip()
    public_key_128 = public_key[2:] if public_key.startswith("04") and len(public_key) == 130 else public_key
    if len(public_key_128) != 128:
        raise AuthError(f"Invalid SM2 public key length: {len(public_key_128)}")
    sm2 = CryptSM2(public_key=public_key_128, private_key="", mode=0)
    encrypted = cast(bytes | None, sm2.encrypt(password.encode("utf-8")))
    if encrypted is None:
        raise AuthError("SM2 encryption failed (gmssl returned None)")
    return "04" + encrypted.hex()


def build_login_payload(
    account: str,
    encrypted_password: str,
    captcha: str | None = None,
) -> dict[str, str]:
    body = {"account": account, "password": encrypted_password}
    if captcha:
        body["captcha"] = captcha
    return body
