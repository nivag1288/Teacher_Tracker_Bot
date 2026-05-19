import os
from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    pass


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise ConfigError(f"Missing required environment variable: {key}")
    return val


DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
DISCORD_GUILD_ID: int = int(_require("DISCORD_GUILD_ID"))
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
DB_PATH: str = os.getenv("DB_PATH", "data/stats.db")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8080"))
