"""Spec-file and CLI-override helpers for task/env creation commands."""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar

import yaml

from ..errors import ValidationError

T = TypeVar("T")

_IGNORED_TOP_LEVEL_KEYS = frozenset({"kind", "version", "api_version"})


def parse_env_assignments(values: list[str] | None, *, option_name: str = "--env") -> dict[str, str]:
    env: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise ValidationError(
                f"{option_name} entries must be KEY=VALUE pairs",
                field_name=option_name,
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message=f"invalid {option_name} entry: {item!r}",
            )
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValidationError(
                f"{option_name} keys cannot be empty",
                field_name=option_name,
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message=f"invalid {option_name} entry: {item!r}",
            )
        env[key] = value
    return env


def parse_json_object_list(values: list[str] | None, *, option_name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in values or []:
        parsed = yaml.safe_load(raw)
        if not isinstance(parsed, dict):
            raise ValidationError(
                f"{option_name} values must parse to JSON/YAML objects",
                field_name=option_name,
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message=f"invalid {option_name} value: {raw!r}",
            )
        result.append(parsed)
    return result


def parse_json_object_merge(values: list[str] | None, *, option_name: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in parse_json_object_list(values, option_name=option_name):
        merged.update(item)
    return merged


def parse_bool_text(value: str | None, *, option_name: str) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise ValidationError(
        f"{option_name} must be true or false",
        field_name=option_name,
        err_code="SDK_CLI_BAD_SPEC_INPUT",
        err_message=f"invalid boolean value for {option_name}: {value!r}",
    )


def ensure_non_negative_int(value: int | None, *, option_name: str) -> None:
    if value is None:
        return
    if value < 0:
        raise ValidationError(
            f"{option_name} must be >= 0",
            field_name=option_name,
            err_code="SDK_CLI_BAD_SPEC_INPUT",
            err_message=f"invalid negative value for {option_name}: {value}",
        )


def ensure_min_int(value: int | None, *, option_name: str, minimum: int) -> None:
    if value is None:
        return
    if value < minimum:
        raise ValidationError(
            f"{option_name} must be >= {minimum}",
            field_name=option_name,
            err_code="SDK_CLI_BAD_SPEC_INPUT",
            err_message=f"invalid value for {option_name}: {value}",
        )


def ensure_positive_float(value: float, *, option_name: str) -> None:
    if value <= 0:
        raise ValidationError(
            f"{option_name} must be > 0",
            field_name=option_name,
            err_code="SDK_CLI_BAD_SPEC_INPUT",
            err_message=f"invalid non-positive value for {option_name}: {value}",
        )


def ensure_port_list(values: list[int] | None, *, option_name: str = "--port") -> None:
    for value in values or []:
        if value < 1 or value > 65535:
            raise ValidationError(
                f"{option_name} values must be in [1, 65535]",
                field_name=option_name,
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message=f"invalid port value for {option_name}: {value}",
            )


def load_mapping_file(
    path: Path | None,
    *,
    resource_name: str,
    unwrap_keys: tuple[str, ...],
) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise ValidationError(
            f"{resource_name} spec file does not exist: {path}",
            field_name="file",
            err_code="SDK_CLI_BAD_SPEC_FILE",
            err_message=f"missing {resource_name} spec file: {path}",
        )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValidationError(
            f"{resource_name} spec file must contain a JSON/YAML object",
            field_name="file",
            err_code="SDK_CLI_BAD_SPEC_FILE",
            err_message=f"invalid {resource_name} spec payload in {path}",
        )
    for key in unwrap_keys:
        nested = payload.get(key)
        if isinstance(nested, dict):
            payload = nested
            break
    return dict(payload)


def merge_spec_mapping(
    base: dict[str, Any],
    *,
    overrides: dict[str, Any] | None = None,
    dict_merges: dict[str, dict[str, Any]] | None = None,
    list_replacements: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    merged = dict(base)
    for key in _IGNORED_TOP_LEVEL_KEYS:
        merged.pop(key, None)
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value
    for key, value in (dict_merges or {}).items():
        if not value:
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(value)
            continue
        if not isinstance(existing, dict):
            raise ValidationError(
                f"{key} must be an object in the spec file",
                field_name=key,
                err_code="SDK_CLI_BAD_SPEC_FILE",
                err_message=f"expected mapping for {key}",
            )
        combined = dict(existing)
        combined.update(value)
        merged[key] = combined
    for key, value in (list_replacements or {}).items():
        if value:
            merged[key] = list(value)
    return merged


def build_spec(
    spec_type: type[T],
    raw_data: dict[str, Any],
    *,
    field_aliases: dict[str, str] | None = None,
    resource_name: str,
) -> T:
    aliases = field_aliases or {}
    valid_fields = {field.name for field in fields(spec_type)}
    normalized: dict[str, Any] = {}
    unknown: list[str] = []
    for key, value in raw_data.items():
        if key in _IGNORED_TOP_LEVEL_KEYS:
            continue
        normalized_key = aliases.get(key, key)
        if normalized_key not in valid_fields:
            unknown.append(key)
            continue
        normalized[normalized_key] = value
    if unknown:
        raise ValidationError(
            f"unknown {resource_name} spec fields: {', '.join(sorted(unknown))}",
            field_name="file",
            err_code="SDK_CLI_BAD_SPEC_FILE",
            err_message=f"unknown {resource_name} spec fields: {', '.join(sorted(unknown))}",
        )
    try:
        return spec_type(**normalized)
    except TypeError as exc:
        raise ValidationError(
            f"invalid {resource_name} spec: {exc}",
            field_name="file",
            err_code="SDK_CLI_BAD_SPEC_FILE",
            err_message=f"invalid {resource_name} spec: {exc}",
        ) from exc
