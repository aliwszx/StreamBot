from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    bot_token: str
    admin_ids: str = ""  # comma-separated list

    # Supabase
    supabase_url: str
    supabase_key: str

    # Server
    webhook_url: str = ""
    webhook_path: str = "/webhook"
    port: int = 8000

    # App
    log_level: str = "INFO"
    cache_ttl: int = 300          # seconds
    items_per_page: int = 5

    @field_validator("bot_token")
    @classmethod
    def token_not_empty(cls, v: str) -> str:
        if not v or v == "your_telegram_bot_token_here":
            raise ValueError("BOT_TOKEN must be set")
        return v

    @property
    def admin_id_list(self) -> List[int]:
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
