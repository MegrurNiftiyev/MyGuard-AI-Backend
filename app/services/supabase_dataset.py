"""
Supabase dataset ingestion service.

Fetches document metadata and binary files (benign vs prompt-injection)
from Supabase PostgreSQL (public.uploads) and Storage (team-files bucket)
for AI model training and testing.
"""

import os
from typing import List, Dict, Optional
from supabase import create_client, Client

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SupabaseDatasetService:
    """Service to interact with Supabase storage and database for training datasets."""

    def __init__(self):
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Lazy-initialize Supabase client."""
        if self._client is None:
            if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured in environment.")
            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return self._client

    @property
    def bucket_name(self) -> str:
        return settings.SUPABASE_STORAGE_BUCKET

    def list_dataset_records(self, category: Optional[str] = None) -> List[Dict]:
        """Fetch metadata records from `public.uploads` table."""
        try:
            query = self.client.from_("uploads").select("*")
            if category in ["benign", "injection"]:
                query = query.eq("category", category)
            response = query.order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error("Failed to list Supabase uploads: %s", str(e))
            raise

    def get_file_download_url(self, storage_path: str) -> str:
        """Get public download URL for a storage object."""
        res = self.client.storage.from_(self.bucket_name).get_public_url(storage_path)
        return res

    def download_file_bytes(self, storage_path: str) -> bytes:
        """Download raw binary content of a file from Supabase storage."""
        response = self.client.storage.from_(self.bucket_name).download(storage_path)
        return response

    def sync_dataset_to_disk(self, target_dir: str = settings.DATASET_BASE_DIR) -> Dict[str, int]:
        """
        Synchronize all clean (benign) and injected (injection) documents
        from Supabase storage to local disk under target_dir/benign and target_dir/injection.
        """
        records = self.list_dataset_records()
        stats = {"benign": 0, "injection": 0, "failed": 0, "skipped": 0}

        for item in records:
            cat = item.get("category")
            path = item.get("storage_path")
            file_name = item.get("file_name")
            record_id = item.get("id")

            if not cat or not path:
                continue

            # Target directory: e.g. ./data/raw/benign or ./data/raw/injection
            cat_dir = os.path.join(target_dir, cat)
            os.makedirs(cat_dir, exist_ok=True)

            safe_filename = f"{record_id}_{file_name}" if record_id else file_name
            local_file_path = os.path.join(cat_dir, safe_filename)

            # Skip download if file already exists locally
            if os.path.exists(local_file_path):
                stats[cat] = stats.get(cat, 0) + 1
                stats["skipped"] += 1
                continue

            try:
                file_bytes = self.download_file_bytes(path)
                with open(local_file_path, "wb") as f:
                    f.write(file_bytes)
                stats[cat] = stats.get(cat, 0) + 1
                logger.info("Downloaded dataset file: %s -> %s", path, local_file_path)
            except Exception as e:
                logger.error("Failed to download dataset file %s: %s", path, str(e))
                stats["failed"] += 1

        return stats


dataset_service = SupabaseDatasetService()
