"""
Application settings loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Service configuration — all values come from env vars or .env file."""

    # MongoDB
    MONGO_URI: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection string",
    )
    DB_NAME: str = Field(
        default="myguard",
        description="MongoDB database name",
    )

    # Service-to-service auth
    INTERNAL_SERVICE_TOKEN: str = Field(
        ...,
        description="Shared secret the Node.js backend sends in X-Internal-Token header",
    )

    # Server
    HOST: str = Field(default="0.0.0.0", description="Bind host")
    PORT: int = Field(default=8000, description="Bind port")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
