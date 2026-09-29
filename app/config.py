from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "./data/surface_map.db")
    ai_provider: str = os.getenv("AI_PROVIDER", "rules-demo")
    ai_base_url: str = os.getenv("AI_BASE_URL", "")
    ai_api_key: str = os.getenv("AI_API_KEY", "")
    ai_model: str = os.getenv("AI_MODEL", "")
    max_crawl_pages: int = int(os.getenv("MAX_CRAWL_PAGES", "12"))
    max_crawl_depth: int = int(os.getenv("MAX_CRAWL_DEPTH", "2"))
    request_delay_seconds: float = float(os.getenv("REQUEST_DELAY_SECONDS", "0.25"))


settings = Settings()
