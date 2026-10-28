"""Environment-driven settings. Mirrors RAG/env_check.py: problems are reported, and STRICT_CONFIG=1
turns them into a startup failure. Secret values are never included in messages."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

_TRUE = ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str
    blob_backend: str
    blob_root: str
    gcs_bucket: str
    strict: bool

    def __repr__(self) -> str:  # keep the connection string (it embeds a password) out of logs
        return (
            f"Settings(database_url={'<set>' if self.database_url else '<unset>'}, "
            f"blob_backend={self.blob_backend!r}, blob_root={self.blob_root!r}, "
            f"gcs_bucket={self.gcs_bucket!r}, strict={self.strict})"
        )


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    get = lambda name, default="": (env.get(name) or default).strip()  # noqa: E731
    return Settings(
        database_url=get("PIPELINE_DATABASE_URL"),
        blob_backend=get("PIPELINE_BLOB_BACKEND", "local").lower(),
        blob_root=get("PIPELINE_BLOB_ROOT", "./.blobs"),
        gcs_bucket=get("PIPELINE_GCS_BUCKET"),
        strict=get("STRICT_CONFIG").lower() in _TRUE,
    )


def check_settings(settings: Settings) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors, warnings = [], []
    if settings.blob_backend not in ("local", "gcs"):
        errors.append(f"PIPELINE_BLOB_BACKEND must be local or gcs, not {settings.blob_backend!r}")
    if settings.blob_backend == "gcs" and not settings.gcs_bucket:
        errors.append("PIPELINE_BLOB_BACKEND=gcs requires PIPELINE_GCS_BUCKET")
    if not settings.database_url:
        warnings.append("PIPELINE_DATABASE_URL is not set: only the in-memory test repository is available")
    elif urlparse(settings.database_url).scheme not in ("postgres", "postgresql"):
        errors.append("PIPELINE_DATABASE_URL must be a postgres:// or postgresql:// URL")
    return errors, warnings


def validate_settings(settings: Settings | None = None) -> Settings:
    settings = settings or load_settings()
    errors, warnings = check_settings(settings)
    for message in warnings:
        print(f"[pipeline config] warning: {message}")
    for message in errors:
        print(f"[pipeline config] error: {message}")
    if errors and settings.strict:
        raise RuntimeError("pipeline configuration invalid (STRICT_CONFIG=1): " + "; ".join(errors))
    return settings
