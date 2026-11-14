"""Environment configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
LOCAL_ENV_PATH = ROOT.parent.parent / "runtime" / "garmin" / ".env"
ENV_PATH = LOCAL_ENV_PATH if LOCAL_ENV_PATH.is_file() else ROOT / ".env"


@dataclass(frozen=True)
class Config:
    email: str
    password: str
    token_dir: Path
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    lookback_days: int
    log_level: str

    @property
    def db_ready(self) -> bool:
        return all((self.pg_host, self.pg_database, self.pg_user, self.pg_password))

    @property
    def token_exists(self) -> bool:
        return (self.token_dir / "garmin_tokens.json").is_file()


def load_config() -> Config:
    load_dotenv(ENV_PATH)

    def db_setting(name: str, fallback: str) -> str:
        return os.getenv(name) or os.getenv(fallback, "")

    token_dir = Path(os.getenv("GARMIN_TOKEN_DIR", "./data/tokens")).expanduser()
    if not token_dir.is_absolute():
        token_dir = ROOT / token_dir
    lookback_days = int(os.getenv("SYNC_LOOKBACK_DAYS", "7"))
    if lookback_days < 1:
        raise ValueError("SYNC_LOOKBACK_DAYS must be at least 1")
    return Config(
        email=os.getenv("GARMIN_EMAIL", "").strip(),
        password=os.getenv("GARMIN_PASSWORD", ""),
        token_dir=token_dir,
        pg_host=db_setting("PGHOST", "MCP_PGHOST").strip(),
        pg_port=int(db_setting("PGPORT", "MCP_PGPORT") or "5432"),
        pg_database=db_setting("PGDATABASE", "MCP_PGDATABASE").strip(),
        pg_user=db_setting("PGUSER", "MCP_PGUSER").strip(),
        pg_password=db_setting("PGPASSWORD", "MCP_PGPASSWORD"),
        lookback_days=lookback_days,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
