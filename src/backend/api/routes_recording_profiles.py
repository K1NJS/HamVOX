from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.models.recording_configuration_models import (
    DiscordWebhookTestResponse,
    RecordingConfigurationResponse,
    RecordingConfigurationUpdateRequest,
    SettingsBackupResponse,
    SiteContentResponse,
    StorageStatsResponse,
    SmbConnectionStatusResponse,
    ThresholdTestResponse,
)
from backend.services.audio_capture_recording_service import AudioCaptureRecordingService
from backend.services.recording_configuration_service import RecordingConfigurationService
from backend.services.admin_auth_service import require_admin, require_public_if_enabled
from backend.services.discord_webhook_service import DiscordWebhookService
from backend.services.smb_backup_service import SmbBackupService


router = APIRouter()


@router.get("/recording-configuration", response_model=RecordingConfigurationResponse, dependencies=[Depends(require_admin)])
def get_recording_configuration() -> RecordingConfigurationResponse:
    service = RecordingConfigurationService()
    return service.get_configuration()


@router.put("/recording-configuration", response_model=RecordingConfigurationResponse, dependencies=[Depends(require_admin)])
def update_recording_configuration(
    payload: RecordingConfigurationUpdateRequest,
) -> RecordingConfigurationResponse:
    service = RecordingConfigurationService()
    return service.update_configuration(payload)


@router.get("/settings/backup", dependencies=[Depends(require_admin)])
def download_settings_backup() -> JSONResponse:
    service = RecordingConfigurationService()
    configuration = service.get_configuration()
    return JSONResponse(
        content=configuration.model_dump(),
        headers={
            "Content-Disposition": 'attachment; filename="hamvox-settings-backup.json"'
        },
    )


@router.post("/settings/restore", response_model=SettingsBackupResponse, dependencies=[Depends(require_admin)])
def restore_settings_backup(
    payload: RecordingConfigurationUpdateRequest,
) -> SettingsBackupResponse:
    service = RecordingConfigurationService()
    service.update_configuration(payload)
    return SettingsBackupResponse(
        ok=True,
        message="Settings restored. Recordings were not changed."
    )


@router.get("/site-content", response_model=SiteContentResponse)
def get_site_content() -> SiteContentResponse:
    service = RecordingConfigurationService()
    return service.get_site_content()


@router.get("/smb/status", response_model=SmbConnectionStatusResponse, dependencies=[Depends(require_admin)])
def get_smb_status() -> SmbConnectionStatusResponse:
    configuration = RecordingConfigurationService().get_configuration()
    status = SmbBackupService().connection_status(configuration)
    return SmbConnectionStatusResponse(**status)


@router.post("/smb/connect", response_model=SmbConnectionStatusResponse, dependencies=[Depends(require_admin)])
def connect_smb_share() -> SmbConnectionStatusResponse:
    smb_service = SmbBackupService()
    configuration = RecordingConfigurationService().get_configuration()
    status = smb_service.connection_status(configuration)
    if status.get("connected"):
        backfill = smb_service.backfill_local_to_backup(configuration)
        status_message = str(status.get("message") or "Connected to SMB share.")
        backfill_message = str(backfill.get("message") or "")
        status["message"] = f"{status_message} {backfill_message}".strip()
    return SmbConnectionStatusResponse(**status)


@router.get("/storage/stats", response_model=StorageStatsResponse, dependencies=[Depends(require_public_if_enabled)])
def get_storage_stats() -> StorageStatsResponse:
    configuration = RecordingConfigurationService().get_configuration()
    payload = SmbBackupService().storage_stats(configuration)
    return StorageStatsResponse(**payload)


@router.post("/discord/test", response_model=DiscordWebhookTestResponse, dependencies=[Depends(require_admin)])
def test_discord_webhook() -> DiscordWebhookTestResponse:
    configuration = RecordingConfigurationService().get_configuration()
    ok, message = DiscordWebhookService().send_test_alert(configuration)
    return DiscordWebhookTestResponse(ok=ok, message=message)


@router.post("/thresholds/test", response_model=ThresholdTestResponse, dependencies=[Depends(require_admin)])
def test_thresholds(
    radio_id: str | None = Query(default=None),
    seconds: float = Query(default=4.0, ge=1.0, le=12.0),
) -> ThresholdTestResponse:
    payload = AudioCaptureRecordingService().run_threshold_test(radio_id=radio_id, sample_seconds=seconds)
    return ThresholdTestResponse(**payload)


@router.get("/thresholds/level", response_model=ThresholdTestResponse, dependencies=[Depends(require_admin)])
def get_live_level(
    radio_id: str | None = Query(default=None),
    seconds: float = Query(default=0.8, ge=0.2, le=2.0),
) -> ThresholdTestResponse:
    payload = AudioCaptureRecordingService().sample_live_level(radio_id=radio_id, sample_seconds=seconds)
    return ThresholdTestResponse(**payload)
