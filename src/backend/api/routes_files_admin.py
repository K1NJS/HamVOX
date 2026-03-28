from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.recordings_browser_models import (
    FileActionResponse,
    FileDeleteRequest,
    RecordingBrowserResponse,
)
from backend.services.admin_auth_service import require_admin
from backend.services.recordings_browser_service import RecordingsBrowserService


router = APIRouter()


@router.get("/files/list", response_model=RecordingBrowserResponse, dependencies=[Depends(require_admin)])
def list_files(path: str = Query("/")) -> RecordingBrowserResponse:
    service = RecordingsBrowserService()
    try:
        return service.list_directory(path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/files/delete", response_model=FileActionResponse, dependencies=[Depends(require_admin)])
def delete_files(payload: FileDeleteRequest) -> FileActionResponse:
    service = RecordingsBrowserService()
    try:
        deleted_paths = service.delete_paths(payload.paths)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return FileActionResponse(
        deleted_paths=deleted_paths,
        message=f"Deleted {len(deleted_paths)} item(s).",
    )


@router.post("/files/clear", response_model=FileActionResponse, dependencies=[Depends(require_admin)])
def clear_all_files() -> FileActionResponse:
    service = RecordingsBrowserService()
    deleted_paths = service.clear_all()
    return FileActionResponse(
        deleted_paths=deleted_paths,
        message=f"Cleared {len(deleted_paths)} item(s).",
    )
