import os
from typing import Iterator
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.services.admin_auth_service import require_public_if_enabled
from backend.services.recording_configuration_service import RecordingConfigurationService


router = APIRouter()


def _live_stream_source_url(mount_name: str) -> str:
    host = os.getenv("ICECAST_SERVICE_HOST", "hamvox-icecast")
    port = os.getenv("ICECAST_SERVICE_PORT", "8000")
    return f"http://{host}:{port}/{mount_name}"


def _stream_chunks(source_url: str) -> Iterator[bytes]:
    request = Request(source_url, headers={"Icy-MetaData": "0"})
    with urlopen(request, timeout=15) as response:  # noqa: S310
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            yield chunk


@router.get("/live-stream", dependencies=[Depends(require_public_if_enabled)])
def proxy_live_stream(radio_id: str | None = Query(default=None)) -> StreamingResponse:
    service = RecordingConfigurationService()
    radio = service.get_radio_profile(radio_id) if radio_id else None
    if radio is None:
        radios = service.get_radio_profiles(enabled_only=True)
        radio = radios[0] if radios else None
    if radio is None:
        raise HTTPException(status_code=404, detail="No enabled radio stream found.")
    source_url = _live_stream_source_url(radio.stream_mount)
    try:
        return StreamingResponse(
            _stream_chunks(source_url),
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Live stream unavailable: {error}") from error
