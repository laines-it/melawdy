from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "melawdy"
    postgres_user: str = "melawdy_app"
    postgres_password: str = "melawdy_local_dev"
    embeddings_enabled: bool = True
    embedding_model_path: str = ""
    embedding_device: str = "cpu"
    search_min_similarity: float = Field(default=0.40, ge=0, le=1)
    session_cookie_secure: bool = False
    session_hours: int = Field(default=8, ge=1, le=168)
    music_check_enabled: bool = False
    music_check_worker_token: str = ""
    music_check_data_dir: str = ".local-data/music-check"
    music_check_max_upload_mb: int = Field(default=32, ge=1, le=128)
    music_check_storage_mb: int = Field(default=512, ge=32, le=10240)
    music_check_max_jobs: int = Field(default=20, ge=1, le=1000)
    music_check_ttl_hours: int = Field(default=24, ge=1, le=168)
    admin_email: str = "admin@melawdy.local"
    admin_password: str = ""
    admin_full_name: str = "Администратор"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
