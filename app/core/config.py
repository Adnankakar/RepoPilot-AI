from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RepoPilot AI"
    debug: bool = True
    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Base directory where repositories are cloned.
    # Override with CLONE_BASE_DIR in .env.
    clone_base_dir: str = "clones"

    # Maximum size in bytes for a single file to be included in discovery.
    # Files larger than this are skipped with a logged reason.
    # Default: 1 MB. Override with MAX_FILE_SIZE_BYTES in .env.
    max_file_size_bytes: int = 1_048_576  # 1 MB

    # Maximum number of files accepted during a single discovery run.
    # Discovery stops cleanly when this count is reached.
    # Default: 10 000. Override with MAX_FILE_COUNT in .env.
    max_file_count: int = 10_000

    # Maximum total size in bytes accepted across all files in one discovery run.
    # Default: 500 MB. Override with MAX_REPO_SIZE_BYTES in .env.
    max_repo_size_bytes: int = 524_288_000  # 500 MB

    # Maximum wall-clock seconds allowed for a single discovery run.
    # Discovery stops cleanly when the deadline is exceeded.
    # Default: 300 s (5 min). Override with MAX_DISCOVERY_SECONDS in .env.
    max_discovery_seconds: float = 300.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()