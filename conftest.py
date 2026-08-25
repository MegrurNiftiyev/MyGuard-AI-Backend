"""
Root conftest — sets environment variables BEFORE any app module is imported.

This avoids pydantic-settings ValidationError during collection.
"""

import os

# Set required env vars before anything else imports app.core.config
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-secret")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "myguard_test")
