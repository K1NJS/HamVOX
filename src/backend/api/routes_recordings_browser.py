from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.models.recordings_browser_models import RecordingBrowserResponse
from backend.services.admin_auth_service import require_public_if_enabled
from backend.services.recordings_browser_service import RecordingsBrowserService


router = APIRouter()


@router.get("/recordings", response_model=RecordingBrowserResponse, dependencies=[Depends(require_public_if_enabled)])
def list_recordings(path: str = Query("/")) -> RecordingBrowserResponse:
    service = RecordingsBrowserService()
    try:
        return service.list_directory(path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/recordings/file", dependencies=[Depends(require_public_if_enabled)])
def get_recording_file(path: str = Query(...)) -> FileResponse:
    service = RecordingsBrowserService()
    try:
        target = service.resolve_file_path(path)
        return FileResponse(target)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
