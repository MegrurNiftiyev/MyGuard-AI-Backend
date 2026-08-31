"""
Application settings loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Service configuration — all values come from env vars or .env file."""

    # Service-to-service auth
    INTERNAL_SERVICE_TOKEN: str = Field(
        ...,
        description="Shared secret the Node.js backend sends in X-Internal-Token header",
    )

    # Logging & Server
    LOG_LEVEL: str = Field(default="INFO", description="Log output level")
    HOST: str = Field(default="0.0.0.0", description="Bind host")
    PORT: int = Field(default=8000, description="Bind port")

    # ML Configuration
    ALLOW_DUMMY_MODEL_FALLBACK: bool = Field(
        default=False,
        description="Allow falling back to DummyModel if Firebase fails. Warning: DO NOT USE IN PROD",
    )

    # CORS / Origin Security
    ALLOWED_ORIGINS: str = Field(
        default="https://mygurad-backend-v2.onrender.com,http://localhost:8000,http://127.0.0.1:8000",
        description="Comma-separated allowed origins",
    )

    # Supabase Data Pipeline Configuration
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="", description="Supabase service role key")
    SUPABASE_ANON_KEY: str = Field(default="", description="Supabase public anon key")
    SUPABASE_STORAGE_BUCKET: str = Field(default="team-files", description="Supabase storage bucket name")
    DATASET_BASE_DIR: str = Field(default="./data/raw", description="Local dataset target directory")

    # Firebase Admin SDK Configuration
    FIREBASE_CREDENTIALS_PATH: str = Field(
        default="./mygurad-firebase-admin.json",
        description="Path to Firebase Admin SDK JSON key file",
    )
    FIREBASE_CREDENTIALS_JSON: str = Field(
        default="",
        description="Raw JSON string of Firebase service account key (useful for cloud envs)",
    )
    FIREBASE_STORAGE_BUCKET: str = Field(
        default="",
        description="Firebase Storage bucket name (e.g. myguard-project.appspot.com)",
    )

    @property
    def SUPABASE_KEY(self) -> str:
        """Return SERVICE_ROLE_KEY if set, otherwise ANON_KEY."""
        return self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_ANON_KEY

    @property
    def ALLOWED_ORIGINS_LIST(self) -> list[str]:
        """Parsed list of allowed CORS origins."""
        if not self.ALLOWED_ORIGINS:
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
