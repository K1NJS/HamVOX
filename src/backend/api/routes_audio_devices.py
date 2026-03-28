from fastapi import APIRouter, Depends

from backend.models.audio_device_models import AudioDeviceInventoryResponse
from backend.services.admin_auth_service import require_admin
from backend.services.audio_device_inventory_service import AudioDeviceInventoryService


router = APIRouter()


@router.get("/audio-devices", response_model=AudioDeviceInventoryResponse, dependencies=[Depends(require_admin)])
def list_audio_devices() -> AudioDeviceInventoryResponse:
    service = AudioDeviceInventoryService()
    return service.list_capture_devices()
