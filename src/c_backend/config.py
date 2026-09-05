from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_db: str = Field(validation_alias="POSTGRES_DB")
    postgres_user: str = Field(validation_alias="POSTGRES_USER")
    postgres_password: str = Field(validation_alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(validation_alias="POSTGRES_PORT")

    celery_broker_url: str = Field(
        validation_alias="CELERY_BROKER_URL"
    )

    whatsapp_verify_token: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_VERIFY_TOKEN",
    )

    whatsapp_app_secret: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_APP_SECRET",
    )

    whatsapp_allowed_senders_raw: str = Field(
        default="",
        validation_alias="WHATSAPP_ALLOWED_SENDERS",
    )

    @property
    def whatsapp_allowed_senders(self) -> set[str]:
        return {
            sender.strip()
            for sender in self.whatsapp_allowed_senders_raw.split(",")
            if sender.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
