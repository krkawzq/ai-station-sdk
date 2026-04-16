from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from platformdirs import user_config_dir

CONFIG_DIR = Path(user_config_dir("aistation"))
AUTH_FILE = CONFIG_DIR / "auth.json"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AuthData:
    base_url: str = "https://aistation.example.invalid"
    account: str = ""
    password: str = ""
    token: str = ""
    token_saved_at: str = ""


@dataclass
class Config:
    default_timeout: float = 15.0
    verify_ssl: bool = False
    image_registry_prefix: str = "192.168.108.1:5000"
    default_project_id: str | None = None
    log_level: str = "INFO"
    max_retries: int = 0
    token_ttl_hours: int = 24


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"malformed JSON object in {path}")
    return data


def _atomic_dump(path: Path, payload: dict[str, object], *, mode: int = 0o600) -> None:
    _ensure_dir(path.parent)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as fh:
        tmp = Path(fh.name)
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    try:
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def load_auth(path: Path | None = None) -> AuthData:
    auth_path = path or AUTH_FILE
    data: dict[str, object] = {}
    if auth_path.exists():
        data = _load_json(auth_path)
    auth = AuthData(
        base_url=str(data.get("base_url", AuthData.base_url)),
        account=str(data.get("account", "")),
        password=str(data.get("password", "")),
        token=str(data.get("token", "")),
        token_saved_at=str(data.get("token_saved_at", "")),
    )
    auth.account = os.getenv("AISTATION_ACCOUNT", auth.account)
    auth.password = os.getenv("AISTATION_PASSWORD", auth.password)
    auth.base_url = (
        os.getenv("AISTATION_BASE_URL")
        or os.getenv("AI_STATION_URL")
        or auth.base_url
    )
    return auth


def save_auth(data: AuthData, path: Path | None = None) -> None:
    auth_path = path or AUTH_FILE
    _atomic_dump(auth_path, asdict(data), mode=0o600)


def load_config(path: Path | None = None) -> Config:
    config_path = path or CONFIG_FILE
    if not config_path.exists():
        return Config()
    data = _load_json(config_path)
    default_project_id = data.get("default_project_id")
    return Config(
        default_timeout=_as_float(data.get("default_timeout"), Config.default_timeout),
        verify_ssl=_as_bool(data.get("verify_ssl"), Config.verify_ssl),
        image_registry_prefix=str(data.get("image_registry_prefix", Config.image_registry_prefix)),
        default_project_id=str(default_project_id) if default_project_id is not None else None,
        log_level=str(data.get("log_level", Config.log_level)),
        max_retries=_as_int(data.get("max_retries"), Config.max_retries),
        token_ttl_hours=_as_int(data.get("token_ttl_hours"), Config.token_ttl_hours),
    )
