from __future__ import annotations

import hashlib

from pydantic import BaseModel

try:
    from ._config import get_env
except ImportError:
    from _config import get_env


class YoudaoCredentials(BaseModel):
    app_key: str
    app_secret: str


class MissingYoudaoCredentials(RuntimeError):
    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__("missing Youdao credentials")


class UnsupportedSignType(RuntimeError):
    def __init__(self, sign_type: str) -> None:
        self.sign_type = sign_type
        super().__init__(f"unsupported Youdao sign type: {sign_type}")


def get_youdao_credentials(service_id: str) -> YoudaoCredentials:
    prefix = service_id.upper().replace("-", "_")
    app_key = get_env(f"YOUDAO_{prefix}_APP_KEY") or get_env("YOUDAO_APP_KEY")
    app_secret = get_env(f"YOUDAO_{prefix}_APP_SECRET") or get_env("YOUDAO_APP_SECRET")
    missing: list[str] = []
    if app_key is None:
        missing.append("app_key")
    if app_secret is None:
        missing.append("app_secret")
    if missing:
        raise MissingYoudaoCredentials(tuple(missing))
    return YoudaoCredentials(app_key=app_key, app_secret=app_secret)


def truncate_input(value: str) -> str:
    size = len(value)
    if size <= 20:
        return value
    return value[:10] + str(size) + value[-10:]


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_youdao_sign_v3(app_key: str, app_secret: str, input_value: str, salt: str, curtime: str) -> str:
    return sha256_hex(app_key + truncate_input(input_value) + salt + curtime + app_secret)


def build_youdao_sign(sign_type: str, app_key: str, app_secret: str, input_value: str, salt: str, curtime: str) -> str:
    if sign_type == "v3":
        return build_youdao_sign_v3(app_key, app_secret, input_value, salt, curtime)
    raise UnsupportedSignType(sign_type)
