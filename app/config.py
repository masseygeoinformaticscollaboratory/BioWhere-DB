from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass
class Settings:
    DB_NAME: str
    DB_USER: str
    DB_HOST: str
    DB_PASSWORD: str
    DB_PORT: int
    DEBUG: bool
    SEARCH_MIN_LEN: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            DB_NAME=os.getenv("PGDATABASE", "biowheregazetteer"),
            DB_USER=os.getenv("PGUSER", "postgres"),
            DB_HOST=os.getenv("PGHOST", "127.0.0.1"),
            DB_PASSWORD=os.getenv("PGPASSWORD", ""),
            DB_PORT=int(os.getenv("PGPORT", "5432")),
            DEBUG=os.getenv("FLASK_DEBUG", "false").lower() == "true",
            SEARCH_MIN_LEN=int(os.getenv("SEARCH_MIN_LEN", "3")),
        )
