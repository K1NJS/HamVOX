import os
import re
import subprocess
from pathlib import Path


class SmbBackupService:
    _REMOTE_HEADER_PATTERN = re.compile(r"^\s*\\(?P<path>.*)\\\*\s*$")
    _REMOTE_FILE_PATTERN = re.compile(
        r"^\s*(?P<name>.+?)\s+(?P<attrs>[A-Za-z]+)\s+(?P<size>\d+)\s+\w+\s+\w+\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4}\s*$"
    )

    def _is_enabled(self, configuration) -> bool:
        return (
            configuration.smb_backup_enabled
            and configuration.smb_host
            and configuration.smb_share
            and configuration.smb_username
        )

    def _archive_root(self) -> Path:
        return Path(os.getenv("HAMVOX_ARCHIVE_ROOT", "/recordings/archive"))

    def _normalize_relative_path(self, path: str) -> str:
        return str(path or "").replace("\\", "/").strip("/")

    def _escape_smb_arg(self, value: str) -> str:
        return str(value or "").replace('"', '\\"')

    def _remote_prefix(self, configuration) -> str:
        return self._normalize_relative_path(configuration.smb_remote_path)

    def _build_remote_path(self, relative_path: str, configuration) -> str:
        normalized_relative = self._normalize_relative_path(relative_path)
        remote_prefix = self._remote_prefix(configuration)
        return f"{remote_prefix}/{normalized_relative}" if remote_prefix else normalized_relative

    def _run_smbclient(self, configuration, command: str) -> subprocess.CompletedProcess[str]:
        share_target = self.share_target(configuration)
        return subprocess.run(
            ["smbclient", share_target, "-U", self._auth(configuration), "-c", command],
            check=False,
            capture_output=True,
            text=True,
        )

    def _parse_remote_audio_listing(self, listing_text: str) -> dict[str, int]:
        current_dir = ""
        discovered: dict[str, int] = {}
        for raw_line in (listing_text or "").splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            header_match = self._REMOTE_HEADER_PATTERN.match(line)
            if header_match:
                current_dir = self._normalize_relative_path(header_match.group("path"))
                continue
            file_match = self._REMOTE_FILE_PATTERN.match(line)
            if not file_match:
                continue
            attrs = file_match.group("attrs").upper()
            if "D" in attrs:
                continue
            name = file_match.group("name").strip()
            if name in {".", ".."}:
                continue
            if not name.lower().endswith(".wav"):
                continue
            relative_path = f"{current_dir}/{name}" if current_dir else name
            normalized = self._normalize_relative_path(relative_path)
            try:
                size = int(file_match.group("size"))
            except ValueError:
                size = 0
            discovered[normalized] = max(size, discovered.get(normalized, 0))
        return discovered

    def _local_audio_index(self) -> dict[str, int]:
        root = self._archive_root()
        root.mkdir(parents=True, exist_ok=True)
        discovered: dict[str, int] = {}
        for entry in root.rglob("*"):
            if not entry.is_file():
                continue
            if entry.suffix.lower() != ".wav":
                continue
            relative_path = self._normalize_relative_path(str(entry.relative_to(root)))
            discovered[relative_path] = entry.stat().st_size
        return discovered

    def share_target(self, configuration) -> str:
        if not configuration.smb_host or not configuration.smb_share:
            return ""
        return f"//{configuration.smb_host}/{configuration.smb_share}"

    def _auth(self, configuration) -> str:
        return f"{configuration.smb_username}%{configuration.smb_password}"

    def connection_status(self, configuration) -> dict[str, str | bool]:
        if not self._is_enabled(configuration):
            return {
                "enabled": False,
                "connected": False,
                "share_target": self.share_target(configuration),
                "message": "SMB backup is disabled.",
            }

        remote_prefix = self._remote_prefix(configuration)
        command = f'cd "{self._escape_smb_arg(remote_prefix)}"; ls' if remote_prefix else "ls"
        result = self._run_smbclient(configuration, command)

        if result.returncode == 0:
            message = "Connected to SMB share."
            if remote_prefix:
                message = f'Connected to SMB share path "{remote_prefix}".'
            share_target = self.share_target(configuration)
            return {
                "enabled": True,
                "connected": True,
                "share_target": share_target,
                "message": message,
            }

        error_text = (result.stderr or result.stdout or "Unknown SMB error").strip()
        share_target = self.share_target(configuration)
        return {
            "enabled": True,
            "connected": False,
            "share_target": share_target,
            "message": error_text,
        }

    def _remote_audio_index(self, configuration) -> tuple[bool, dict[str, int], str]:
        if not self._is_enabled(configuration):
            return False, {}, "SMB backup is disabled."

        remote_prefix = self._remote_prefix(configuration)
        command_parts: list[str] = []
        if remote_prefix:
            command_parts.append(f'cd "{self._escape_smb_arg(remote_prefix)}"')
        command_parts.extend(["recurse ON", "ls"])
        result = self._run_smbclient(configuration, "; ".join(command_parts))
        if result.returncode != 0:
            return False, {}, (result.stderr or result.stdout or "Unknown SMB error").strip()
        return True, self._parse_remote_audio_listing(result.stdout or ""), "SMB listing loaded."

    def _safe_remote_relative_path(self, relative_path: str) -> str:
        requested = str(relative_path or "").strip()
        requested = requested if requested.startswith("/") else f"/{requested}" if requested else "/"
        normalized = self._normalize_relative_path(requested)
        if not normalized:
            return ""
        parts = [part for part in normalized.split("/") if part]
        for part in parts:
            if part in {".", ".."}:
                raise ValueError("Path escapes SMB recordings root")
        return "/".join(parts)

    def _parse_remote_directory_listing(self, listing_text: str) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for raw_line in (listing_text or "").splitlines():
            line = raw_line.rstrip()
            file_match = self._REMOTE_FILE_PATTERN.match(line)
            if not file_match:
                continue
            name = file_match.group("name").strip()
            if name in {".", ".."}:
                continue
            attrs = file_match.group("attrs").upper()
            is_dir = "D" in attrs
            try:
                size = int(file_match.group("size"))
            except ValueError:
                size = 0
            entries.append(
                {
                    "name": name,
                    "type": "dir" if is_dir else "file",
                    "size": 0 if is_dir else size,
                    "mtime": 0,
                }
            )
        entries.sort(key=lambda item: (item["type"] != "dir", str(item["name"]).lower()))
        return entries

    def list_directory(self, relative_path: str, configuration) -> dict[str, object]:
        if not self._is_enabled(configuration):
            raise ValueError("SMB backup is disabled.")
        status = self.connection_status(configuration)
        if not status.get("connected"):
            raise ValueError(str(status.get("message") or "SMB share is not reachable."))

        requested = self._safe_remote_relative_path(relative_path)
        remote_path = self._build_remote_path(requested, configuration) if requested else self._remote_prefix(configuration)
        command_parts: list[str] = []
        if remote_path:
            command_parts.append(f'cd "{self._escape_smb_arg(remote_path)}"')
        command_parts.append("ls")
        result = self._run_smbclient(configuration, "; ".join(command_parts))
        if result.returncode != 0:
            raise ValueError((result.stderr or result.stdout or "Unable to list SMB directory.").strip())

        items = self._parse_remote_directory_listing(result.stdout or "")
        response_items: list[dict[str, object]] = []
        for item in items:
            child_relative = f"{requested}/{item['name']}" if requested else str(item["name"])
            normalized_child = self._normalize_relative_path(child_relative)
            response_items.append(
                {
                    "name": item["name"],
                    "type": item["type"],
                    "path": "/" + normalized_child if normalized_child else "/",
                    "size": int(item["size"]),
                    "mtime": int(item["mtime"]),
                }
            )
        cwd = "/" + requested if requested else "/"
        return {"cwd": cwd, "items": response_items}

    def download_file_to_cache(self, relative_path: str, configuration) -> Path:
        if not self._is_enabled(configuration):
            raise ValueError("SMB backup is disabled.")
        status = self.connection_status(configuration)
        if not status.get("connected"):
            raise ValueError(str(status.get("message") or "SMB share is not reachable."))

        requested = self._safe_remote_relative_path(relative_path)
        if not requested:
            raise ValueError("Requested path is not a file")

        remote_path = self._build_remote_path(requested, configuration)
        cache_root = Path(os.getenv("HAMVOX_SMB_CACHE_ROOT", "/tmp/hamvox-smb-cache"))
        host_segment = re.sub(r"[^A-Za-z0-9._-]+", "_", str(configuration.smb_host or "host"))
        share_segment = re.sub(r"[^A-Za-z0-9._-]+", "_", str(configuration.smb_share or "share"))
        cache_file = cache_root / host_segment / share_segment / requested
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        command_parts = [
            f'lcd "{self._escape_smb_arg(str(cache_file.parent))}"',
            f'get "{self._escape_smb_arg(remote_path)}" "{self._escape_smb_arg(cache_file.name)}"',
        ]
        result = self._run_smbclient(configuration, "; ".join(command_parts))
        if result.returncode != 0 or not cache_file.exists():
            raise ValueError((result.stderr or result.stdout or "Unable to download SMB file.").strip())
        return cache_file

    def _day_folder_from_relative_path(self, relative_path: str) -> str:
        normalized = self._normalize_relative_path(relative_path)
        if not normalized:
            return ""
        return normalized.split("/", 1)[0]

    def _sorted_day_folders_from_index(self, audio_index: dict[str, int]) -> list[str]:
        day_folders = {self._day_folder_from_relative_path(path) for path in audio_index}
        return sorted(folder for folder in day_folders if folder)

    def backfill_local_to_backup(self, configuration) -> dict[str, object]:
        if not self._is_enabled(configuration):
            return {
                "ok": False,
                "uploaded_audio_files": 0,
                "uploaded_total_bytes": 0,
                "failed_audio_files": 0,
                "message": "SMB backup is disabled.",
            }

        ok, remote_index, listing_message = self._remote_audio_index(configuration)
        if not ok:
            return {
                "ok": False,
                "uploaded_audio_files": 0,
                "uploaded_total_bytes": 0,
                "failed_audio_files": 0,
                "message": listing_message,
            }

        local_index = self._local_audio_index()
        missing_paths = sorted(set(local_index.keys()) - set(remote_index.keys()))
        if not missing_paths:
            return {
                "ok": True,
                "uploaded_audio_files": 0,
                "uploaded_total_bytes": 0,
                "failed_audio_files": 0,
                "message": "SMB already has all locally stored .wav files.",
            }

        archive_root = self._archive_root()
        uploaded_files = 0
        uploaded_bytes = 0
        failed_files = 0
        first_error = ""
        for relative_path in missing_paths:
            local_file = archive_root / relative_path
            success, message = self.upload_file(local_file, Path(relative_path), configuration)
            if success:
                uploaded_files += 1
                uploaded_bytes += local_index.get(relative_path, 0)
            else:
                failed_files += 1
                if not first_error:
                    first_error = message

        if failed_files:
            message = (
                f"Backfill uploaded {uploaded_files} file(s) to SMB with {failed_files} failure(s)."
            )
            if first_error:
                message = f"{message} First error: {first_error}"
            return {
                "ok": uploaded_files > 0,
                "uploaded_audio_files": uploaded_files,
                "uploaded_total_bytes": uploaded_bytes,
                "failed_audio_files": failed_files,
                "message": message,
            }

        return {
            "ok": True,
            "uploaded_audio_files": uploaded_files,
            "uploaded_total_bytes": uploaded_bytes,
            "failed_audio_files": 0,
            "message": f"Backfill uploaded {uploaded_files} missing local .wav file(s) to SMB.",
        }

    def import_preview(self, configuration) -> dict[str, object]:
        if not self._is_enabled(configuration):
            return {
                "ok": False,
                "enabled": False,
                "connected": False,
                "remote_date_folders": [],
                "local_date_folders": [],
                "importable_date_folders": [],
                "message": "SMB backup is disabled.",
            }

        ok, remote_index, listing_message = self._remote_audio_index(configuration)
        local_index = self._local_audio_index()
        local_days = self._sorted_day_folders_from_index(local_index)
        if not ok:
            return {
                "ok": False,
                "enabled": True,
                "connected": False,
                "remote_date_folders": [],
                "local_date_folders": local_days,
                "importable_date_folders": [],
                "message": listing_message,
            }

        remote_days = self._sorted_day_folders_from_index(remote_index)
        local_days_set = set(local_days)
        importable_days = [day for day in remote_days if day not in local_days_set]
        if not remote_days:
            message = "SMB connected, but no dated .wav folders were found."
        elif not importable_days:
            message = "No missing date folders to import. Local archive already has all SMB dates."
        else:
            message = f"Found {len(importable_days)} date folder(s) on SMB that are missing locally."

        return {
            "ok": True,
            "enabled": True,
            "connected": True,
            "remote_date_folders": remote_days,
            "local_date_folders": local_days,
            "importable_date_folders": importable_days,
            "message": message,
        }

    def import_missing_dates(self, configuration, date_folders: list[str] | None = None) -> dict[str, object]:
        preview = self.import_preview(configuration)
        if not preview.get("ok"):
            return {
                "ok": False,
                "copied_audio_files": 0,
                "copied_total_bytes": 0,
                "failed_audio_files": 0,
                "imported_date_folders": [],
                "message": str(preview.get("message") or "SMB import preview failed."),
            }

        importable_days = set(preview.get("importable_date_folders") or [])
        if not importable_days:
            return {
                "ok": True,
                "copied_audio_files": 0,
                "copied_total_bytes": 0,
                "failed_audio_files": 0,
                "imported_date_folders": [],
                "message": "No missing date folders to import.",
            }

        requested_days = {
            self._normalize_relative_path(day)
            for day in (date_folders or [])
            if self._normalize_relative_path(day)
        }
        if requested_days:
            target_days = sorted(day for day in importable_days if day in requested_days)
        else:
            target_days = sorted(importable_days)
        if not target_days:
            return {
                "ok": False,
                "copied_audio_files": 0,
                "copied_total_bytes": 0,
                "failed_audio_files": 0,
                "imported_date_folders": [],
                "message": "None of the requested date folders are importable.",
            }

        ok, remote_index, listing_message = self._remote_audio_index(configuration)
        if not ok:
            return {
                "ok": False,
                "copied_audio_files": 0,
                "copied_total_bytes": 0,
                "failed_audio_files": 0,
                "imported_date_folders": [],
                "message": listing_message,
            }
        local_index = self._local_audio_index()
        missing_paths = [
            path
            for path in sorted(remote_index.keys())
            if path not in local_index and self._day_folder_from_relative_path(path) in target_days
        ]
        if not missing_paths:
            return {
                "ok": True,
                "copied_audio_files": 0,
                "copied_total_bytes": 0,
                "failed_audio_files": 0,
                "imported_date_folders": [],
                "message": "Selected date folders are already present locally.",
            }

        archive_root = self._archive_root()
        archive_root.mkdir(parents=True, exist_ok=True)
        remote_prefix = self._remote_prefix(configuration)
        copied_files = 0
        copied_bytes = 0
        failed_files = 0
        first_error = ""

        for relative_path in missing_paths:
            local_target = archive_root / relative_path
            local_target.parent.mkdir(parents=True, exist_ok=True)
            command_seq: list[str] = []
            if remote_prefix:
                command_seq.append(f'cd "{self._escape_smb_arg(remote_prefix)}"')
            command_seq.append(f'lcd "{self._escape_smb_arg(str(archive_root))}"')
            command_seq.append(
                f'get "{self._escape_smb_arg(relative_path)}" "{self._escape_smb_arg(relative_path)}"'
            )
            result = self._run_smbclient(configuration, "; ".join(command_seq))
            if result.returncode == 0 and local_target.exists():
                copied_files += 1
                copied_bytes += remote_index.get(relative_path, local_target.stat().st_size)
            else:
                failed_files += 1
                if not first_error:
                    first_error = (result.stderr or result.stdout or "Unknown SMB error").strip()

        if failed_files:
            message = (
                f"Imported {copied_files} file(s) from SMB with {failed_files} failure(s)."
            )
            if first_error:
                message = f"{message} First error: {first_error}"
            return {
                "ok": copied_files > 0,
                "copied_audio_files": copied_files,
                "copied_total_bytes": copied_bytes,
                "failed_audio_files": failed_files,
                "imported_date_folders": target_days,
                "message": message,
            }

        return {
            "ok": True,
            "copied_audio_files": copied_files,
            "copied_total_bytes": copied_bytes,
            "failed_audio_files": 0,
            "imported_date_folders": target_days,
            "message": f"Imported {copied_files} .wav file(s) from SMB date folder(s): {', '.join(target_days)}.",
        }

    def storage_stats(self, configuration) -> dict[str, object]:
        local_index = self._local_audio_index()
        response: dict[str, object] = {
            "ok": True,
            "local_audio_files": len(local_index),
            "local_total_bytes": sum(local_index.values()),
            "smb_enabled": bool(configuration.smb_backup_enabled),
            "smb_connected": False,
            "smb_audio_files": 0,
            "smb_total_bytes": 0,
            "message": "Storage stats loaded.",
        }
        if not self._is_enabled(configuration):
            if configuration.smb_backup_enabled:
                response["message"] = "SMB is enabled but incomplete. Fill SMB host/share/user to read SMB usage."
            return response

        ok, remote_index, listing_message = self._remote_audio_index(configuration)
        if not ok:
            response["message"] = listing_message
            return response

        response["smb_connected"] = True
        response["smb_audio_files"] = len(remote_index)
        response["smb_total_bytes"] = sum(remote_index.values())
        return response

    def upload_file(self, local_file: Path, relative_path: Path, configuration) -> tuple[bool, str]:
        if not self._is_enabled(configuration):
            return False, "SMB backup is disabled."

        remote_path = self._build_remote_path(str(relative_path), configuration)

        parent_parts = Path(remote_path).parent.parts
        commands: list[str] = []
        current = ""
        for part in parent_parts:
            current = f"{current}/{part}" if current else part
            commands.append(f'mkdir "{self._escape_smb_arg(current)}"')
        commands.append(f'put "{self._escape_smb_arg(str(local_file))}" "{self._escape_smb_arg(remote_path)}"')

        result = self._run_smbclient(configuration, "; ".join(commands))
        if result.returncode == 0:
            return True, f"SMB backup saved to {remote_path}"
        error_text = (result.stderr or result.stdout or "Unknown SMB error").strip()
        return False, error_text
