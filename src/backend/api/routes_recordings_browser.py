from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.models.recordings_browser_models import RecordingBrowserResponse
from backend.services.admin_auth_service import require_public_if_enabled
from backend.services.recording_configuration_service import RecordingConfigurationService
from backend.services.recordings_browser_service import RecordingsBrowserService
from backend.services.smb_backup_service import SmbBackupService


router = APIRouter()


@router.get("/recordings", response_model=RecordingBrowserResponse, dependencies=[Depends(require_public_if_enabled)])
def list_recordings(
    path: str = Query("/"),
    source: str = Query("local"),
) -> RecordingBrowserResponse:
    source_name = (source or "local").strip().lower()
    try:
        if source_name == "smb":
            configuration = RecordingConfigurationService().get_configuration()
            payload = SmbBackupService().list_directory(path, configuration)
            return RecordingBrowserResponse(**payload)
        if source_name != "local":
            raise ValueError("Invalid recordings source.")
        service = RecordingsBrowserService()
        return service.list_directory(path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/recordings/file", dependencies=[Depends(require_public_if_enabled)])
def get_recording_file(
    path: str = Query(...),
    source: str = Query("local"),
) -> FileResponse:
    source_name = (source or "local").strip().lower()
    try:
        if source_name == "smb":
            configuration = RecordingConfigurationService().get_configuration()
            target = SmbBackupService().download_file_to_cache(path, configuration)
            return FileResponse(target)
        if source_name != "local":
            raise ValueError("Invalid recordings source.")
        service = RecordingsBrowserService()
        target = service.resolve_file_path(path)
        return FileResponse(target)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
