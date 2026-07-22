"""Runtime configuration for the Polaris Chief of Staff API.

Configuration is read from environment variables so development, staging, and
builder deployments do not require source-code changes.
"""

from dataclasses import dataclass
import os


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("POLARIS_ENV", "development")
    service_name: str = os.getenv(
        "POLARIS_SERVICE_NAME", "Polaris Chief of Staff API"
    )
    version: str = os.getenv("POLARIS_VERSION", "0.8.0-alpha")
    organization_slug: str = os.getenv(
        "POLARIS_ORGANIZATION_SLUG", "mor-logistics"
    )
    cors_origins: tuple[str, ...] = _csv_env(
        "POLARIS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )


settings = Settings()
