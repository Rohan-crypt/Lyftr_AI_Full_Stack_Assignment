import os

# Database URL (use writable /tmp/app.db on Vercel serverless if not overridden)
_default_db = "sqlite:////tmp/app.db" if os.getenv("VERCEL") else "sqlite:///./data/app.db"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

# Parse SQLite file path from URL
def get_db_path(url: str) -> str:
    if url.startswith("sqlite:////"):
        # Unix absolute path e.g. sqlite:////data/app.db -> /data/app.db
        return "/" + url[len("sqlite:////"):]
    elif url.startswith("sqlite:///"):
        # e.g. sqlite:///./data/app.db -> ./data/app.db
        return url[len("sqlite:///"): ]
    return url

DB_FILE_PATH = get_db_path(DATABASE_URL)

# LLM API Keys pool
# Format in env: key1,key2,... -> assigned ids key_1, key_2, ...
raw_keys = os.getenv("LLM_API_KEYS", "dummy_key_1,dummy_key_2")
parsed_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
if not parsed_keys:
    parsed_keys = ["dummy_key_1", "dummy_key_2"]

KEY_POOL = [(f"key_{i+1}", key) for i, key in enumerate(parsed_keys)]

# Allowed CORS origins
raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]

# Failure simulation toggle
ENABLE_FAILURE_SIMULATION = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() in ("true", "1", "yes")

# Default model
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini/gemini-flash-lite-latest")

# Default system prompt
DEFAULT_SYSTEM_PROMPT = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful and concise AI assistant.")
