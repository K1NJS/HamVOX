from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes_audio_devices import router as audio_devices_router
from backend.api.routes_files_admin import router as files_admin_router
from backend.api.routes_live_stream import router as live_stream_router
from backend.api.routes_recordings_browser import router as recordings_browser_router
from backend.api.routes_recording_profiles import router as recording_profiles_router
from backend.api.routes_system import router as system_router
from backend.services.admin_auth_service import require_admin, require_public_if_enabled


app = FastAPI(title="HamVOX", version="0.1.0")

app.include_router(system_router, prefix="/api")
app.include_router(audio_devices_router, prefix="/api")
app.include_router(files_admin_router, prefix="/api")
app.include_router(live_stream_router, prefix="/api")
app.include_router(recordings_browser_router, prefix="/api")
app.include_router(recording_profiles_router, prefix="/api")
app.mount("/static", StaticFiles(directory="/app/src/frontend"), name="static")


@app.get("/", include_in_schema=False, dependencies=[Depends(require_public_if_enabled)])
def frontend_index() -> FileResponse:
    return FileResponse("/app/src/frontend/index.html")


@app.get("/settings", include_in_schema=False, dependencies=[Depends(require_admin)])
def frontend_settings() -> FileResponse:
    return FileResponse("/app/src/frontend/settings.html")


@app.get("/files", include_in_schema=False, dependencies=[Depends(require_admin)])
def frontend_files() -> FileResponse:
    return FileResponse("/app/src/frontend/files.html")
