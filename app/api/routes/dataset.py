"""
Dataset API Router.

Provides endpoints to inspect, download, and synchronize prompt injection
and benign document datasets from Supabase for AI model training.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, Depends

from app.api.dependencies import verify_internal_service
from app.services.supabase_dataset import dataset_service

router = APIRouter(prefix="/api/v1/dataset", tags=["AI Training Dataset"])


@router.get(
    "/files",
    summary="List dataset metadata",
    dependencies=[Depends(verify_internal_service)],
)
def get_dataset_files(
    category: Optional[str] = Query(
        None, description="Filter dataset by 'benign' or 'injection'"
    )
):
    """Retrieves metadata of uploaded clean and injected document datasets from Supabase."""
    try:
        return dataset_service.list_dataset_records(category=category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/file/{record_id}/download",
    summary="Download single dataset file",
    dependencies=[Depends(verify_internal_service)],
)
def download_single_file(record_id: str):
    """Download binary content of a specific dataset file by record ID."""
    try:
        records = dataset_service.list_dataset_records()
        target = next((r for r in records if r["id"] == record_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Dataset file not found.")

        content = dataset_service.download_file_bytes(target["storage_path"])
        return Response(
            content=content,
            media_type=target.get("mime_type", "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{target["file_name"]}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.post(
    "/sync",
    summary="Synchronize Supabase dataset to local training directory",
    dependencies=[Depends(verify_internal_service)],
)
def sync_dataset():
    """
    Downloads all missing clean (benign) and injected documents from Supabase
    to local directory (`./data/raw/benign/` and `./data/raw/injection/`)
    ready for AI model training.
    """
    try:
        summary = dataset_service.sync_dataset_to_disk()
        return {
            "status": "success",
            "message": "Dataset successfully synchronized from Supabase.",
            "synced_counts": summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync process failed: {str(e)}")
