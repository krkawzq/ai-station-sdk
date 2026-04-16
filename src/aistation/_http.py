from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests  # type: ignore[import-untyped]

from .errors import AiStationError, TransportError
from .pagination import page_param_for
from .transport import check_flag


def paginate(
    session: requests.Session,
    base_url: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    page_size: int = 50,
    max_pages: int = 1000,
    timeout: float = 15.0,
    page_param: str | None = None,
) -> Iterator[dict[str, Any]]:
    query: dict[str, Any] = dict(params or {})
    query.setdefault("pageSize", page_size)
    resolved_page_param = page_param or page_param_for(path)
    page = 1
    while page <= max_pages:
        query[resolved_page_param] = page
        try:
            response = session.get(f"{base_url}{path}", params=query, timeout=timeout)
            body = response.json()
        except requests.RequestException as exc:
            raise TransportError(str(exc), path=path) from exc
        except ValueError as exc:
            raise AiStationError(f"invalid JSON response from {path}", path=path) from exc

        data = check_flag(body, path)
        if not isinstance(data, dict):
            break
        rows = data.get("data")
        if not isinstance(rows, list):
            break
        for row in rows:
            if isinstance(row, dict):
                yield row
        total_pages = int(data.get("totalPages") or 1)
        if page >= total_pages:
            break
        page += 1
