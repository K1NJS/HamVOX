import os
import shutil
from pathlib import Path

from backend.models.recordings_browser_models import (
    RecordingBrowserItem,
    RecordingBrowserResponse,
)


class RecordingsBrowserService:
    def _recordings_root(self) -> Path:
        return Path(os.getenv("HAMVOX_ARCHIVE_ROOT", "/recordings/archive"))

    def _safe_path(self, relative_path: str) -> Path:
        root = self._recordings_root().resolve()
        requested = relative_path.strip() or "/"
        requested = requested if requested.startswith("/") else f"/{requested}"
        target = (root / requested.lstrip("/")).resolve()
        if root != target and root not in target.parents:
            raise ValueError("Path escapes recordings root")
        return target

    def list_directory(self, relative_path: str = "/") -> RecordingBrowserResponse:
        root = self._recordings_root().resolve()
        target = self._safe_path(relative_path)
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            raise ValueError("Requested path is not a directory")

        items: list[RecordingBrowserItem] = []
        for entry in sorted(
            target.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        ):
            stat = entry.stat()
            relative_entry_path = "/" + str(entry.relative_to(root)).replace("\\", "/")
            items.append(
                RecordingBrowserItem(
                    name=entry.name,
                    type="dir" if entry.is_dir() else "file",
                    path=relative_entry_path,
                    size=0 if entry.is_dir() else stat.st_size,
                    mtime=int(stat.st_mtime),
                )
            )

        current_relative_path = "/" + str(target.relative_to(root)).replace("\\", "/")
        if current_relative_path == "/.":
            current_relative_path = "/"

        return RecordingBrowserResponse(cwd=current_relative_path, items=items)

    def resolve_file_path(self, relative_path: str) -> Path:
        target = self._safe_path(relative_path)
        if not target.exists():
            raise ValueError("Requested file does not exist")
        if not target.is_file():
            raise ValueError("Requested path is not a file")
        return target

    def delete_paths(self, relative_paths: list[str]) -> list[str]:
        deleted_paths: list[str] = []
        for relative_path in relative_paths:
            target = self._safe_path(relative_path)
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            deleted_paths.append(relative_path)
        return deleted_paths

    def clear_all(self) -> list[str]:
        root = self._recordings_root().resolve()
        deleted_paths: list[str] = []
        if not root.exists():
            return deleted_paths
        for entry in root.iterdir():
            relative_entry_path = "/" + str(entry.relative_to(root)).replace("\\", "/")
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            deleted_paths.append(relative_entry_path)
        return deleted_paths
