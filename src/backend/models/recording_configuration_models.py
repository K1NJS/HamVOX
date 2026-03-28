from pydantic import BaseModel, Field, model_validator


class RadioProfileResponse(BaseModel):
    id: str
    name: str
    enabled: bool = True
    audio_device_name: str
    audio_gain_db: float
    min_clip_seconds: float
    max_clip_seconds: float
    stop_after_silence_seconds: float
    start_threshold_db: float
    stop_threshold_db: float
    vox_start: str
    vox_stop: str
    stream_mount: str


class RadioProfileUpdateRequest(BaseModel):
    id: str
    name: str
    enabled: bool = True
    audio_device_name: str
    audio_gain_db: float
    min_clip_seconds: float
    max_clip_seconds: float
    stop_after_silence_seconds: float
    start_threshold_db: float
    stop_threshold_db: float

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.max_clip_seconds < self.min_clip_seconds:
            raise ValueError("Max clip seconds must be greater than or equal to min clip seconds.")
        if self.stop_after_silence_seconds <= 0:
            raise ValueError("Stop after silence must be greater than 0 seconds.")
        return self


class RecordingConfigurationResponse(BaseModel):
    site_callsign: str
    site_tagline: str
    site_info_title: str
    site_info_text: str
    radios: list[RadioProfileResponse] = Field(default_factory=list)
    smb_backup_enabled: bool
    storage_mode: str
    smb_host: str
    smb_share: str
    smb_username: str
    smb_password: str
    smb_remote_path: str
    discord_webhook_enabled: bool
    discord_webhook_url: str
    discord_alert_mode: str
    discord_alert_template: str


class RecordingConfigurationUpdateRequest(BaseModel):
    site_callsign: str
    site_tagline: str
    site_info_title: str
    site_info_text: str
    radios: list[RadioProfileUpdateRequest] = Field(default_factory=list)
    smb_backup_enabled: bool
    storage_mode: str
    smb_host: str
    smb_share: str
    smb_username: str
    smb_password: str
    smb_remote_path: str
    discord_webhook_enabled: bool
    discord_webhook_url: str
    discord_alert_mode: str
    discord_alert_template: str

    @model_validator(mode="after")
    def validate_radios(self):
        ids = set()
        devices = set()
        for radio in self.radios:
            if radio.id in ids:
                raise ValueError("Each radio profile must have a unique id.")
            ids.add(radio.id)
            device_name = (radio.audio_device_name or "").strip()
            if device_name and device_name in devices:
                raise ValueError("Each radio profile must use a different audio device.")
            if device_name:
                devices.add(device_name)
        return self


class SmbConnectionStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    share_target: str
    message: str


class DiscordWebhookTestResponse(BaseModel):
    ok: bool
    message: str


class SettingsBackupResponse(BaseModel):
    ok: bool
    message: str


class ThresholdTestResponse(BaseModel):
    ok: bool
    message: str
    peak_db: float | None = None
    rms_db: float | None = None
    gain_db: float | None = None
    start_threshold_db: float | None = None
    stop_threshold_db: float | None = None
    stop_after_silence_seconds: float | None = None
    would_trigger_start: bool | None = None


class SiteRadioSummary(BaseModel):
    id: str
    name: str
    enabled: bool
    stream_mount: str


class SiteContentResponse(BaseModel):
    site_callsign: str
    site_tagline: str
    site_info_title: str
    site_info_text: str
    radios: list[SiteRadioSummary] = Field(default_factory=list)
