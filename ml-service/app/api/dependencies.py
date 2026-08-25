"""
Shared dependencies for API routes.
"""

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_internal_service(x_internal_token: str = Header(...)):
    """Validate the service-to-service shared secret.

    Every route in this service is internal-only — called exclusively by the
    Node.js backend, never by end users. This dependency enforces a simple
    shared-secret header check instead of user-facing JWT auth.
    """
    if x_internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized service call")
