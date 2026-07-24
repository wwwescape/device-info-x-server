from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    environment: str = "production"
    debug: bool = False
    enable_docs: bool = False
    log_level: str = "INFO"
    domain: str = "localhost"

    # PostgreSQL
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "device_info_x"
    postgres_user: str = "device_info_x"
    postgres_password: str = ""

    # Auth / JWT
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    password_pepper: str = ""

    # Pairing / registration
    server_setup_token: str = ""
    partner_code_expire_minutes: int = 15

    # Media storage
    media_root: str = "/data/media"
    max_image_size_mb: int = 15
    max_voice_size_mb: int = 20
    max_video_size_mb: int = 150
    max_avatar_size_mb: int = 5
    max_locker_file_size_mb: int = 50
    max_document_size_mb: int = 50
    # "x-accel": download endpoint sets X-Accel-Redirect and Nginx serves the
    # bytes (production, see nginx/conf.d/app.conf). "direct": FastAPI streams
    # the file itself — used when there's no Nginx in front (local dev).
    media_serve_mode: str = "x-accel"

    # Firebase Cloud Messaging
    firebase_service_account_json: str = ""

    # Coturn
    turn_static_secret: str = ""
    turn_urls: str = ""
    turn_credential_ttl_seconds: int = 3600

    # In-app update check — a fixed GitHub "latest release" asset URL (e.g.
    # https://github.com/<owner>/<repo>/releases/latest/download/app-release.apk), never a
    # specific release's own URL, which would need updating every publish. Kept server-side
    # rather than hardcoded client-side so a broken/moved link can be fixed here without shipping
    # a new APK — see the TODOS.md writeup this was built from.
    apk_download_url: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def turn_urls_list(self) -> list[str]:
        return [url.strip() for url in self.turn_urls.split(",") if url.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
