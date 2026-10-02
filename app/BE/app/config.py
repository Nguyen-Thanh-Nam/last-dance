from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = tuple(origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:2222,http://localhost:2222").split(",") if origin.strip())
    database_path: str = os.getenv("DATABASE_PATH", "./data/surface_map.db")
    ai_provider: str = os.getenv("AI_PROVIDER", "rules-demo")
    ai_base_url: str = os.getenv("AI_BASE_URL", "")
    ai_api_key: str = os.getenv("AI_API_KEY", "")
    ai_model: str = os.getenv("AI_MODEL", "")
    max_crawl_pages: int = int(os.getenv("MAX_CRAWL_PAGES", "12"))
    max_crawl_depth: int = int(os.getenv("MAX_CRAWL_DEPTH", "2"))
    request_delay_seconds: float = float(os.getenv("REQUEST_DELAY_SECONDS", "0.25"))
    enable_rdap: bool = os.getenv("ENABLE_RDAP", "false").casefold() in {"1", "true", "yes"}
    allow_private_lab: bool = os.getenv("ALLOW_PRIVATE_LAB", "false").casefold() in {"1", "true", "yes"}

    def __post_init__(self):
        if not 1 <= self.max_crawl_pages <= 100:
            raise ValueError("MAX_CRAWL_PAGES must be between 1 and 100")
        if not 0 <= self.max_crawl_depth <= 5:
            raise ValueError("MAX_CRAWL_DEPTH must be between 0 and 5")
        if not 0 <= self.request_delay_seconds <= 10:
            raise ValueError("REQUEST_DELAY_SECONDS must be between 0 and 10")


settings = Settings()
