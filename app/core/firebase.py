"""
Firebase Admin SDK initialization module.

Supports loading credentials from:
1. JSON key file path (FIREBASE_CREDENTIALS_PATH)
2. Raw JSON string from environment variable (FIREBASE_CREDENTIALS_JSON)
"""

import json
import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore, storage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_firebase_app: Optional[firebase_admin.App] = None


def init_firebase() -> Optional[firebase_admin.App]:
    """Initialize Firebase Admin SDK app if credentials are provided."""
    global _firebase_app

    if _firebase_app is not None or firebase_admin._apps:
        logger.info("Firebase Admin SDK already initialized.")
        return firebase_admin.get_app()

    cred = None

    # Option 1: File path
    if settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
        try:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            logger.info("Loaded Firebase credentials from file: %s", settings.FIREBASE_CREDENTIALS_PATH)
        except Exception as e:
            logger.error("Failed to load Firebase credentials from file %s: %s", settings.FIREBASE_CREDENTIALS_PATH, str(e))

    # Option 2: JSON string from ENV
    elif settings.FIREBASE_CREDENTIALS_JSON:
        try:
            cert_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(cert_dict)
            logger.info("Loaded Firebase credentials from environment JSON string.")
        except Exception as e:
            logger.error("Failed to parse Firebase credentials from env JSON string: %s", str(e))

    options = {}
    if settings.FIREBASE_STORAGE_BUCKET:
        options["storageBucket"] = settings.FIREBASE_STORAGE_BUCKET

    if cred:
        try:
            _firebase_app = firebase_admin.initialize_app(cred, options=options if options else None)
            logger.info("Firebase Admin SDK successfully initialized.")
            return _firebase_app
        except Exception as e:
            logger.error("Failed to initialize Firebase Admin SDK app: %s", str(e))
    else:
        logger.warning(
            "Firebase credentials not found (checked path: '%s'). "
            "Firebase Admin SDK skipped. Place key file at path or set FIREBASE_CREDENTIALS_JSON.",
            settings.FIREBASE_CREDENTIALS_PATH,
        )

    return None


def get_firestore_db():
    """Return initialized Firebase Firestore client, or None if not initialized."""
    if not firebase_admin._apps:
        init_firebase()
    if firebase_admin._apps:
        try:
            return firestore.client()
        except Exception as e:
            logger.error("Failed to access Firestore client: %s", str(e))
    return None


def get_storage_bucket():
    """Return initialized Firebase Storage bucket, or None if not initialized."""
    if not firebase_admin._apps:
        init_firebase()
    if firebase_admin._apps:
        try:
            bucket_name = settings.FIREBASE_STORAGE_BUCKET or None
            return storage.bucket(name=bucket_name)
        except Exception as e:
            logger.error("Failed to access Storage bucket: %s", str(e))
    return None
