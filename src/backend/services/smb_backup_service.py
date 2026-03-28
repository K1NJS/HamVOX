import subprocess
from pathlib import Path


class SmbBackupService:
    def _is_enabled(self, configuration) -> bool:
        return (
            configuration.smb_backup_enabled
            and configuration.smb_host
            and configuration.smb_share
            and configuration.smb_username
        )

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

        share_target = self.share_target(configuration)
        command = 'cd "{}"; ls'.format(configuration.smb_remote_path.strip("/")) if configuration.smb_remote_path.strip("/") else "ls"
        result = subprocess.run(
            ["smbclient", share_target, "-U", self._auth(configuration), "-c", command],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            message = "Connected to SMB share."
            if configuration.smb_remote_path.strip("/"):
                message = f'Connected to SMB share path "{configuration.smb_remote_path.strip("/")}".'
            return {
                "enabled": True,
                "connected": True,
                "share_target": share_target,
                "message": message,
            }

        error_text = (result.stderr or result.stdout or "Unknown SMB error").strip()
        return {
            "enabled": True,
            "connected": False,
            "share_target": share_target,
            "message": error_text,
        }

    def upload_file(self, local_file: Path, relative_path: Path, configuration) -> tuple[bool, str]:
        if not self._is_enabled(configuration):
            return False, "SMB backup is disabled."

        share_target = self.share_target(configuration)
        remote_prefix = configuration.smb_remote_path.strip("/").replace("\\", "/")
        remote_relative = str(relative_path).replace("\\", "/")
        remote_path = f"{remote_prefix}/{remote_relative}" if remote_prefix else remote_relative

        parent_parts = Path(remote_path).parent.parts
        commands: list[str] = []
        current = ""
        for part in parent_parts:
            current = f"{current}/{part}" if current else part
            commands.append(f'mkdir "{current}"')
        commands.append(f'put "{local_file}" "{remote_path}"')

        result = subprocess.run(
            ["smbclient", share_target, "-U", self._auth(configuration), "-c", "; ".join(commands)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, f"SMB backup saved to {remote_path}"
        error_text = (result.stderr or result.stdout or "Unknown SMB error").strip()
        return False, error_text
