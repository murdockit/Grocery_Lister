from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:////data/app.db"
    data_dir: Path = Path("/data")

    kroger_client_id: str = ""
    kroger_client_secret: str = ""
    kroger_location_id: str = ""
    mock_kroger: bool = False

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    output_mode: str = "todoist,email"
    todoist_api_token: str = ""
    todoist_api_base_url: str = "https://api.todoist.com/api/v1"
    todoist_project_name: str = "Weekly Deals"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    notify_email: str = ""
    email_from: str = ""

    tz: str = "America/New_York"
    run_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] = "wed"
    run_hour: int = Field(default=7, ge=0, le=23)

    watchlist_path: Path = Path("/data/watchlist.yaml")
    http_timeout_seconds: float = 30.0

    @field_validator("output_mode")
    @classmethod
    def normalize_output_mode(cls, value: str) -> str:
        modes = [mode.strip().lower() for mode in value.split(",") if mode.strip()]
        return ",".join(dict.fromkeys(modes))

    @property
    def output_modes(self) -> list[str]:
        return [mode for mode in self.output_mode.split(",") if mode]

    @property
    def kroger_location_ids(self) -> list[str]:
        return list(
            dict.fromkeys(
                location_id.strip()
                for location_id in self.kroger_location_id.split(",")
                if location_id.strip()
            )
        )

    @property
    def effective_email_from(self) -> str:
        return self.email_from or self.smtp_user or self.notify_email


@lru_cache
def get_settings() -> Settings:
    return Settings()
