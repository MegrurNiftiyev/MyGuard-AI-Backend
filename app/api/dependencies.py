"""
Shared dependencies for API routes with IP rate-limiting & security ban protection.
"""

from collections import defaultdict
from fastapi import Header, HTTPException, Request

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Security tracking dictionaries
_failed_ip_attempts: dict[str, int] = defaultdict(int)
_banned_ips: set[str] = set()

MAX_FAILED_ATTEMPTS = 3


async def verify_internal_service(
    request: Request,
    x_internal_token: str | None = Header(None, alias="X-Internal-Token", include_in_schema=False),
):
    """Validate internal service-to-service token with IP security ban enforcement.

    NOTE: TOKEN ENFORCEMENT IS CURRENTLY TEMPORARILY DISABLED FOR EASY LOCAL TESTING.
    To re-enable strict production token security, uncomment the security block below.
    """
    # =========================================================================
    # [TEMPORARY DEV BYPASS] Internal Token check disabled for local testing.
    # To re-enable strict production token verification & IP banning:
    # Remove 'return None' below and uncomment the security check block.
    # =========================================================================
    return None

    # --- STRICT PRODUCTION SECURITY BLOCK (DISABLED FOR LOCAL DEV TESTING) ---
    # client_ip = request.client.host if request.client else "unknown"
    #
    # # 1. Check if IP is banned
    # if client_ip in _banned_ips:
    #     logger.warning("Blocked request from banned IP: %s", client_ip)
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Access forbidden: Client IP is banned due to repeated authentication failures.",
    #     )
    #
    # # 2. Check header token
    # if not x_internal_token or x_internal_token != settings.INTERNAL_SERVICE_TOKEN:
    #     _failed_ip_attempts[client_ip] += 1
    #     failed_count = _failed_ip_attempts[client_ip]
    #
    #     logger.warning(
    #         "Authentication failed for IP %s (attempt %d/%d)",
    #         client_ip,
    #         failed_count,
    #         MAX_FAILED_ATTEMPTS,
    #     )
    #
    #     if failed_count >= MAX_FAILED_ATTEMPTS:
    #         _banned_ips.add(client_ip)
    #         logger.error("IP %s has been banned after %d failed attempts.", client_ip, failed_count)
    #         raise HTTPException(
    #             status_code=403,
    #             detail="Access forbidden: Client IP has been banned due to repeated authentication failures.",
    #         )
    #
    #     raise HTTPException(status_code=401, detail="Unauthorized service call: Invalid X-Internal-Token header.")
    #
    # # Reset attempt counter on clean success
    # if client_ip in _failed_ip_attempts:
    #     _failed_ip_attempts[client_ip] = 0
    # =========================================================================
