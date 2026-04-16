from __future__ import annotations

import os

import requests  # type: ignore[import-untyped]
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def build_session(verify: bool = False) -> requests.Session:
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        os.environ.pop(key, None)
    session = requests.Session()
    session.verify = verify
    session.trust_env = False
    return session
