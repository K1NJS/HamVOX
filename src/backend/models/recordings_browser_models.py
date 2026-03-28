from pydantic import BaseModel


class RecordingBrowserItem(BaseModel):
    name: str
    type: str
    path: str
    size: int
    mtime: int


class RecordingBrowserResponse(BaseModel):
    cwd: str
    items: list[RecordingBrowserItem]


class FileDeleteRequest(BaseModel):
    paths: list[str]


class FileActionResponse(BaseModel):
    deleted_paths: list[str]
    message: str
