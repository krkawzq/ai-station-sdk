from __future__ import annotations

import os

import httpx


def build_async_session(verify: bool = False) -> httpx.AsyncClient:
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        os.environ.pop(key, None)
    return httpx.AsyncClient(verify=verify, trust_env=False)
