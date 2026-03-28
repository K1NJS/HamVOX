import math
import os
import re

from backend.models.recording_configuration_models import (
    RadioProfileResponse,
    RecordingConfigurationUpdateRequest,
    RecordingConfigurationResponse,
    SiteContentResponse,
    SiteRadioSummary,
)
from backend.services.audio_device_inventory_service import AudioDeviceInventoryService
from backend.services.application_settings_store import ApplicationSettingsStore


class RecordingConfigurationService:
    DEFAULT_START_DURATION_SECONDS = 0.1
    DEFAULT_STOP_DURATION_SECONDS = 1.5
    DEFAULT_AUDIO_GAIN_DB = 0.0
    DEFAULT_MAX_CLIP_SECONDS = 30.0
    DEFAULT_SITE_CALLSIGN = "HamVOX"
    DEFAULT_SITE_TAGLINE = "Live & Archived Radio Recordings"
    DEFAULT_SITE_INFO_TITLE = "About HamVOX"
    DEFAULT_SITE_INFO_TEXT = (
        "HamVOX is a self-hosted radio monitoring app that lets you stream live "
        "audio, save timestamped recordings, organize multiple radio profiles, "
        "mirror archives to SMB storage, and send Discord alerts when new "
        "activity is captured."
    )
    DEFAULT_DISCORD_ALERT_TEMPLATE = "Radio: {radio_name}\nPath: {path}\nLength: {length}"

    def __init__(self) -> None:
        self.settings_store = ApplicationSettingsStore()
        self.audio_device_inventory_service = AudioDeviceInventoryService()

    def _extract_percent_value(self, threshold_expression: str) -> float:
        token = threshold_expression.strip().split()[-1]
        if token.endswith("%"):
            return float(token[:-1])
        return float(token)

    def _percent_to_db(self, percent_value: float) -> float:
        if percent_value <= 0:
            return -100.0
        return round(20 * math.log10(percent_value / 100.0), 1)

    def _db_to_percent_string(self, db_value: float) -> str:
        percent_value = 100 * math.pow(10, db_value / 20.0)
        formatted = f"{percent_value:.5f}".rstrip("0").rstrip(".")
        return f"{formatted}%"

    def _normalize_device_name(self, device_name: str) -> str:
        if device_name.startswith("hw:"):
            return "plughw:" + device_name[len("hw:"):]
        return device_name

    def _vox_start_expression(self, db_value: float) -> str:
        return f"1 {self.DEFAULT_START_DURATION_SECONDS:.1f} {self._db_to_percent_string(db_value)}"

    def _extract_duration_value(self, threshold_expression: str, fallback: float) -> float:
        parts = threshold_expression.strip().split()
        if len(parts) >= 2:
            try:
                return float(parts[1])
            except ValueError:
                return fallback
        return fallback

    def _vox_stop_expression(self, db_value: float, silence_seconds: float | None = None) -> str:
        stop_seconds = self.DEFAULT_STOP_DURATION_SECONDS if silence_seconds is None else float(silence_seconds)
        return f"1 {stop_seconds:.1f} {self._db_to_percent_string(db_value)}"

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "radio"

    def _stream_mount_for(self, radio_id: str, radio_name: str) -> str:
        return f"radio-{self._slugify(radio_name or radio_id)}.mp3"

    def _default_radio(self) -> RadioProfileResponse:
        vox_start = os.getenv("HAMVOX_VOX_START", "1 0.1 0.10%")
        vox_stop = os.getenv("HAMVOX_VOX_STOP", "1 1.5 0.30%")
        start_threshold_db = self._percent_to_db(self._extract_percent_value(vox_start))
        stop_threshold_db = self._percent_to_db(self._extract_percent_value(vox_stop))
        stop_after_silence_seconds = self._extract_duration_value(vox_stop, self.DEFAULT_STOP_DURATION_SECONDS)
        radio_name = os.getenv("HAMVOX_PROFILE_LABEL", "Radio 1")
        default_device_name = self._normalize_device_name(
            os.getenv("HAMVOX_AUDIO_DEVICE_NAME", "").strip()
        )
        if default_device_name and not self.audio_device_inventory_service.has_capture_device(default_device_name):
            default_device_name = ""
        return RadioProfileResponse(
            id="radio1",
            name=radio_name,
            enabled=True,
            audio_device_name=default_device_name,
            audio_gain_db=float(os.getenv("HAMVOX_AUDIO_GAIN_DB", str(self.DEFAULT_AUDIO_GAIN_DB))),
            min_clip_seconds=float(os.getenv("HAMVOX_MIN_CLIP_SECONDS", "1.0")),
            max_clip_seconds=float(os.getenv("HAMVOX_MAX_CLIP_SECONDS", str(self.DEFAULT_MAX_CLIP_SECONDS))),
            stop_after_silence_seconds=float(
                os.getenv("HAMVOX_STOP_AFTER_SILENCE_SECONDS", str(stop_after_silence_seconds))
            ),
            start_threshold_db=start_threshold_db,
            stop_threshold_db=stop_threshold_db,
            vox_start=vox_start,
            vox_stop=vox_stop,
            stream_mount=self._stream_mount_for("radio1", radio_name),
        )

    def default_configuration(self) -> RecordingConfigurationResponse:
        return RecordingConfigurationResponse(
            site_callsign=os.getenv("HAMVOX_SITE_CALLSIGN", self.DEFAULT_SITE_CALLSIGN),
            site_tagline=os.getenv("HAMVOX_SITE_TAGLINE", self.DEFAULT_SITE_TAGLINE),
            site_info_title=os.getenv("HAMVOX_SITE_INFO_TITLE", self.DEFAULT_SITE_INFO_TITLE),
            site_info_text=os.getenv("HAMVOX_SITE_INFO_TEXT", self.DEFAULT_SITE_INFO_TEXT),
            radios=[self._default_radio()],
            smb_backup_enabled=os.getenv("HAMVOX_SMB_BACKUP_ENABLED", "false").lower() == "true",
            storage_mode=os.getenv("HAMVOX_STORAGE_MODE", "local"),
            smb_host=os.getenv("HAMVOX_SMB_HOST", ""),
            smb_share=os.getenv("HAMVOX_SMB_SHARE", ""),
            smb_username=os.getenv("HAMVOX_SMB_USERNAME", ""),
            smb_password=os.getenv("HAMVOX_SMB_PASSWORD", ""),
            smb_remote_path=os.getenv("HAMVOX_SMB_REMOTE_PATH", ""),
            discord_webhook_enabled=os.getenv("HAMVOX_DISCORD_WEBHOOK_ENABLED", "false").lower() == "true",
            discord_webhook_url=os.getenv("HAMVOX_DISCORD_WEBHOOK_URL", ""),
            discord_alert_mode=os.getenv("HAMVOX_DISCORD_ALERT_MODE", "per_clip"),
            discord_alert_template=os.getenv(
                "HAMVOX_DISCORD_ALERT_TEMPLATE",
                self.DEFAULT_DISCORD_ALERT_TEMPLATE,
            ),
        )

    def _response_radio_from_payload(self, payload: dict, fallback: RadioProfileResponse, used_mounts: set[str]) -> RadioProfileResponse:
        radio_id = str(payload.get("id") or fallback.id)
        radio_name = str(payload.get("name") or fallback.name)
        stream_mount = str(payload.get("stream_mount") or self._stream_mount_for(radio_id, radio_name))
        while stream_mount in used_mounts:
            stream_mount = self._stream_mount_for(radio_id, f"{radio_name}-{len(used_mounts) + 1}")
        used_mounts.add(stream_mount)
        return RadioProfileResponse(
            id=radio_id,
            name=radio_name,
            enabled=bool(payload.get("enabled", True)),
            audio_device_name=self._normalize_device_name(
                str(payload.get("audio_device_name") or fallback.audio_device_name)
            ),
            audio_gain_db=float(payload.get("audio_gain_db", fallback.audio_gain_db)),
            min_clip_seconds=float(payload.get("min_clip_seconds", fallback.min_clip_seconds)),
            max_clip_seconds=float(payload.get("max_clip_seconds", fallback.max_clip_seconds)),
            stop_after_silence_seconds=float(
                payload.get("stop_after_silence_seconds", fallback.stop_after_silence_seconds)
            ),
            start_threshold_db=float(payload.get("start_threshold_db", fallback.start_threshold_db)),
            stop_threshold_db=float(payload.get("stop_threshold_db", fallback.stop_threshold_db)),
            vox_start=str(payload.get("vox_start") or self._vox_start_expression(float(payload.get("start_threshold_db", fallback.start_threshold_db)))),
            vox_stop=str(
                payload.get("vox_stop")
                or self._vox_stop_expression(
                    float(payload.get("stop_threshold_db", fallback.stop_threshold_db)),
                    float(payload.get("stop_after_silence_seconds", fallback.stop_after_silence_seconds)),
                )
            ),
            stream_mount=stream_mount,
        )

    def _migrate_saved_values(self, saved_values: dict, defaults: RecordingConfigurationResponse) -> dict:
        migrated = dict(saved_values)
        if "radios" in migrated:
            return migrated

        fallback_radio = defaults.radios[0]
        migrated["radios"] = [
            self._response_radio_from_payload(
                {
                    "id": "radio1",
                    "name": migrated.get("radio_name") or migrated.get("profile_label") or fallback_radio.name,
                    "enabled": True,
                    "audio_device_name": migrated.get("audio_device_name", fallback_radio.audio_device_name),
                    "audio_gain_db": migrated.get("audio_gain_db", fallback_radio.audio_gain_db),
                    "min_clip_seconds": migrated.get("min_clip_seconds", fallback_radio.min_clip_seconds),
                    "max_clip_seconds": migrated.get("max_clip_seconds", fallback_radio.max_clip_seconds),
                    "stop_after_silence_seconds": migrated.get(
                        "stop_after_silence_seconds", fallback_radio.stop_after_silence_seconds
                    ),
                    "start_threshold_db": migrated.get("start_threshold_db", fallback_radio.start_threshold_db),
                    "stop_threshold_db": migrated.get("stop_threshold_db", fallback_radio.stop_threshold_db),
                    "vox_start": migrated.get("vox_start", fallback_radio.vox_start),
                    "vox_stop": migrated.get("vox_stop", fallback_radio.vox_stop),
                },
                fallback_radio,
                set(),
            ).model_dump()
        ]
        return migrated

    def get_configuration(self) -> RecordingConfigurationResponse:
        defaults = self.default_configuration()
        saved_values = self.settings_store.load()
        if not saved_values:
            return defaults

        migrated_values = self._migrate_saved_values(saved_values, defaults)
        if migrated_values != saved_values:
            self.settings_store.save(migrated_values)
        saved_values = migrated_values
        saved_radios = saved_values.get("radios") or []
        fallback_map = {radio.id: radio for radio in defaults.radios}
        used_mounts: set[str] = set()
        radios = [
            self._response_radio_from_payload(
                payload=radio_payload,
                fallback=fallback_map.get(str(radio_payload.get("id") or "radio1"), defaults.radios[0]),
                used_mounts=used_mounts,
            )
            for radio_payload in saved_radios
        ]
        if not radios:
            radios = defaults.radios

        merged = defaults.model_copy(
            update={
                "site_callsign": saved_values.get("site_callsign", defaults.site_callsign),
                "site_tagline": saved_values.get("site_tagline", defaults.site_tagline),
                "site_info_title": saved_values.get("site_info_title", defaults.site_info_title),
                "site_info_text": saved_values.get("site_info_text", defaults.site_info_text),
                "radios": radios,
                "smb_backup_enabled": saved_values.get("smb_backup_enabled", defaults.smb_backup_enabled),
                "storage_mode": saved_values.get("storage_mode", defaults.storage_mode),
                "smb_host": saved_values.get("smb_host", defaults.smb_host),
                "smb_share": saved_values.get("smb_share", defaults.smb_share),
                "smb_username": saved_values.get("smb_username", defaults.smb_username),
                "smb_password": saved_values.get("smb_password", defaults.smb_password),
                "smb_remote_path": saved_values.get("smb_remote_path", defaults.smb_remote_path),
                "discord_webhook_enabled": saved_values.get("discord_webhook_enabled", defaults.discord_webhook_enabled),
                "discord_webhook_url": saved_values.get("discord_webhook_url", defaults.discord_webhook_url),
                "discord_alert_mode": saved_values.get("discord_alert_mode", defaults.discord_alert_mode),
                "discord_alert_template": saved_values.get("discord_alert_template", defaults.discord_alert_template),
            }
        )
        return merged

    def update_configuration(
        self,
        payload: RecordingConfigurationUpdateRequest,
    ) -> RecordingConfigurationResponse:
        radios: list[RadioProfileResponse] = []
        used_mounts: set[str] = set()
        for radio in payload.radios:
            radios.append(
                RadioProfileResponse(
                    id=radio.id,
                    name=radio.name,
                    enabled=radio.enabled,
                    audio_device_name=self._normalize_device_name(radio.audio_device_name),
                    audio_gain_db=radio.audio_gain_db,
                    min_clip_seconds=radio.min_clip_seconds,
                    max_clip_seconds=radio.max_clip_seconds,
                    stop_after_silence_seconds=radio.stop_after_silence_seconds,
                    start_threshold_db=radio.start_threshold_db,
                    stop_threshold_db=radio.stop_threshold_db,
                    vox_start=self._vox_start_expression(radio.start_threshold_db),
                    vox_stop=self._vox_stop_expression(radio.stop_threshold_db, radio.stop_after_silence_seconds),
                    stream_mount=self._response_radio_from_payload(
                        {"id": radio.id, "name": radio.name},
                        self._default_radio(),
                        used_mounts,
                    ).stream_mount,
                )
            )
        if not radios:
            radios = [self._default_radio()]

        updated_configuration = RecordingConfigurationResponse(
            site_callsign=payload.site_callsign,
            site_tagline=payload.site_tagline,
            site_info_title=payload.site_info_title,
            site_info_text=payload.site_info_text,
            radios=radios,
            smb_backup_enabled=payload.smb_backup_enabled,
            storage_mode="smb" if payload.smb_backup_enabled else "local",
            smb_host=payload.smb_host,
            smb_share=payload.smb_share,
            smb_username=payload.smb_username,
            smb_password=payload.smb_password,
            smb_remote_path=payload.smb_remote_path,
            discord_webhook_enabled=payload.discord_webhook_enabled,
            discord_webhook_url=payload.discord_webhook_url,
            discord_alert_mode=payload.discord_alert_mode,
            discord_alert_template=payload.discord_alert_template,
        )
        self.settings_store.save(updated_configuration.model_dump())
        return updated_configuration

    def get_site_content(self) -> SiteContentResponse:
        configuration = self.get_configuration()
        return SiteContentResponse(
            site_callsign=configuration.site_callsign,
            site_tagline=configuration.site_tagline,
            site_info_title=configuration.site_info_title,
            site_info_text=configuration.site_info_text,
            radios=[
                SiteRadioSummary(
                    id=radio.id,
                    name=radio.name,
                    enabled=radio.enabled,
                    stream_mount=radio.stream_mount,
                )
                for radio in configuration.radios
            ],
        )

    def get_radio_profiles(self, enabled_only: bool = False) -> list[RadioProfileResponse]:
        configuration = self.get_configuration()
        if not enabled_only:
            return configuration.radios
        return [radio for radio in configuration.radios if radio.enabled]

    def get_radio_profile(self, radio_id: str) -> RadioProfileResponse | None:
        for radio in self.get_configuration().radios:
            if radio.id == radio_id:
                return radio
        return None
