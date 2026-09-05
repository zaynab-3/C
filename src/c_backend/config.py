from functools import lru_cache
from typing import Literal

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

    whatsapp_access_token: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_ACCESS_TOKEN",
    )

    whatsapp_phone_number_id: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_PHONE_NUMBER_ID",
    )

    ai_provider: Literal["gemini", "openai"] = Field(
        default="gemini",
        validation_alias="AI_PROVIDER",
    )

    gemini_api_key: str | None = Field(
        default=None,
        validation_alias="GEMINI_API_KEY",
    )

    gemini_model: str = Field(
        default="gemini-3.8-flash",
        validation_alias="GEMINI_MODEL",
    )

    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )

    openai_model: str | None = Field(
        default=None,
        validation_alias="OPENAI_MODEL",
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
