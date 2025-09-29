import json
import logging

from langchain_core.embeddings import Embeddings
from starlette.config import Config, undefined

env = Config()
logger = logging.getLogger(__name__)

IS_TESTING = env("IS_TESTING", cast=str, default="").lower() == "true"

if IS_TESTING:
    SUPABASE_URL = ""
    SUPABASE_KEY = ""
else:
    SUPABASE_URL = env("SUPABASE_URL", cast=str, default=undefined)
    SUPABASE_KEY = env("SUPABASE_SERVICE_KEY", cast=str, default=undefined)

# Service Account Configuration
# Static API key for external service authentication (n8n, Zapier, etc.)
SERVICE_ACCOUNT_KEY = env("LANGCONNECT_SERVICE_ACCOUNT_KEY", cast=str, default="")
# Backward compatibility - also check the old name
if not SERVICE_ACCOUNT_KEY:
    SERVICE_ACCOUNT_KEY = env("LANGCONNECT_SERVICE_ACCOUNT_KEY", cast=str, default="")

# GCP Image Storage Configuration
IMAGE_STORAGE_ENABLED = env("IMAGE_STORAGE_ENABLED", cast=str, default="false").lower() == "true"

def get_embeddings() -> Embeddings:
    """Get the embeddings instance based on the environment."""
    if IS_TESTING:
        from langchain_core.embeddings import DeterministicFakeEmbedding

        return DeterministicFakeEmbedding(size=512)
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings()


DEFAULT_EMBEDDINGS = get_embeddings()
DEFAULT_COLLECTION_NAME = "default_collection"


# Database configuration
POSTGRES_HOST = env("LANGCONNECT_POSTGRES_HOST", cast=str, default="localhost")
POSTGRES_PORT = env("LANGCONNECT_POSTGRES_PORT", cast=int, default="5432")
POSTGRES_USER = env("LANGCONNECT_POSTGRES_USER", cast=str, default="langchain")
POSTGRES_PASSWORD = env("LANGCONNECT_POSTGRES_PASSWORD", cast=str, default="langchain")
POSTGRES_DB = env("LANGCONNECT_POSTGRES_DB", cast=str, default="langchain_test")
POSTGRES_SCHEMA = env("LANGCONNECT_POSTGRES_SCHEMA", cast=str, default="public")

# Read allowed origins from environment variable
ALLOW_ORIGINS_JSON = env("ALLOW_ORIGINS", cast=str, default="")

if ALLOW_ORIGINS_JSON:
    ALLOWED_ORIGINS = json.loads(ALLOW_ORIGINS_JSON.strip())
    logger.info(f"ALLOW_ORIGINS environment variable set to: {ALLOW_ORIGINS_JSON}")
else:
    ALLOWED_ORIGINS = "http://localhost:3000"
    logger.info("ALLOW_ORIGINS environment variable not set, using default: http://localhost:3000")
