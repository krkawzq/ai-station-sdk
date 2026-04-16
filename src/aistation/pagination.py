from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PaginationPolicy:
    page_param: str = "pageNum"
    page_size_param: str = "pageSize"
    fast_page_param: str = "page"
    fast_page_size_param: str = "pageSize"
    supports_fast_list: bool = True


_DEFAULT_POLICY = PaginationPolicy()
_POLICIES: dict[str, PaginationPolicy] = {
    "/api/iresource/v1/train": PaginationPolicy(page_param="page"),
    "/api/iresource/v1/work-platform/history": PaginationPolicy(page_param="page"),
    "/api/iresource/v1/work-platform/goto-train-job": PaginationPolicy(page_param="page"),
    "/api/iresource/v1/node-group": PaginationPolicy(page_param="page"),
}


def policy_for(path: str) -> PaginationPolicy:
    return _POLICIES.get(path, _DEFAULT_POLICY)


def page_param_for(path: str) -> str:
    return policy_for(path).page_param


def build_fast_list_query(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy_for(path)
    query: dict[str, Any] = dict(params or {})
    if policy.supports_fast_list:
        query.setdefault(policy.fast_page_param, -1)
        query.setdefault(policy.fast_page_size_param, -1)
    return query


def strip_pagination_params(params: dict[str, Any] | None = None) -> dict[str, Any]:
    stripped = dict(params or {})
    for key in ("page", "pageNum", "pageSize"):
        stripped.pop(key, None)
    return stripped
