import json
from pathlib import Path
from urllib import error, request


class DiscordWebhookService:
    def _render_message(
        self,
        configuration,
        relative_path: Path,
        clip_length_seconds: float,
        alert_reason: str,
        radio_name: str,
    ) -> str:
        alert_type = "New hour recording started" if alert_reason == "new_hour" else "New recording saved"
        minutes = int(clip_length_seconds // 60)
        seconds = int(clip_length_seconds % 60)
        length = f"{minutes}:{seconds:02d}"
        template = (
            getattr(configuration, "discord_alert_template", "") or
            "Radio: {radio_name}\nPath: {path}\nLength: {length}"
        )
        return template.format(
            type=alert_type,
            radio_name=radio_name or "Radio",
            path=relative_path.as_posix(),
            length=length,
        )

    def send_message(self, webhook_url: str, message: str) -> tuple[bool, str]:
        if not webhook_url:
            return False, "Discord webhook URL is blank."
        payload = json.dumps({"content": message}).encode("utf-8")
        req = request.Request(
            webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "hamvox/1.0",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10):
                return True, "Discord webhook sent."
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace").strip()
            suffix = f" {body}" if body else ""
            return False, f"Discord webhook HTTP {exc.code}.{suffix}"
        except Exception as exc:
            return False, f"Discord webhook failed: {exc}"

    def send_recording_alert(
        self,
        configuration,
        relative_path: Path,
        clip_length_seconds: float,
        alert_reason: str,
        radio_name: str,
    ) -> tuple[bool, str]:
        if not getattr(configuration, "discord_webhook_enabled", False):
            return False, "Discord webhook disabled."

        webhook_url = (getattr(configuration, "discord_webhook_url", "") or "").strip()
        if not webhook_url:
            return False, "Discord webhook URL is blank."
        message = self._render_message(configuration, relative_path, clip_length_seconds, alert_reason, radio_name)
        return self.send_message(webhook_url, message)

    def send_test_alert(self, configuration) -> tuple[bool, str]:
        relative_path = Path("TestHour/Test_Clip.wav")
        message = self._render_message(configuration, relative_path, 8.0, "per_clip", "Primary Radio")
        return self.send_message((getattr(configuration, "discord_webhook_url", "") or "").strip(), message)
