from pydantic import BaseModel, Field, model_validator

DEFAULT_TRANSCRIPTION_OPENAI_HOUR_SUMMARY_PROMPT = (
    "Create a concise hourly summary for public-safety scanner traffic for {label}.\n"
    "Use only information from the transcript.\n\n"
    "Output format:\n"
    "Headline: one short sentence.\n"
    "Top Calls:\n"
    "- 8 to 15 bullets.\n"
    "- Each bullet should be short and to the point.\n"
    "- Include location and outcome when available.\n"
    "Call Details:\n"
    "- 4 to 10 bullets.\n"
    "- 1 to 2 short sentences per bullet.\n\n"
    "Rules:\n"
    "- No fluff, no filler, no long narratives.\n"
    "- No disclaimer line.\n"
    "- Do not invent details.\n\n"
    "Transcript:\n"
    "{transcript}\n"
)

DEFAULT_TRANSCRIPTION_OPENAI_DAY_SUMMARY_PROMPT = (
    "Create a concise daily summary for public-safety scanner traffic for {day_label}.\n"
    "Use only information from the hourly summaries.\n\n"
    "Output format:\n"
    "Daily Headline: one short sentence.\n"
    "Major Events:\n"
    "- 10 to 20 short bullets highlighting the most important incidents.\n"
    "Incident Details:\n"
    "- 8 to 16 bullets.\n"
    "- 1 to 2 short sentences per bullet.\n\n"
    "Rules:\n"
    "- Keep it direct and to the point.\n"
    "- No long paragraphs.\n"
    "- No disclaimer line.\n"
    "- Do not invent details.\n\n"
    "Hourly summaries:\n"
    "{hourly_summaries}\n"
)


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
    ui_theme: str
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
    transcription_enabled: bool
    transcription_provider: str
    transcription_openai_api_key: str
    transcription_openai_base_url: str
    transcription_openai_transcribe_model: str
    transcription_openai_summary_model: str
    transcription_openai_language: str
    transcription_openai_max_files_per_pass: int
    transcription_openai_sleep_seconds: float
    transcription_openai_hour_summary_prompt: str
    transcription_openai_day_summary_prompt: str


class RecordingConfigurationUpdateRequest(BaseModel):
    site_callsign: str
    site_tagline: str
    site_info_title: str
    site_info_text: str
    ui_theme: str = "dark"
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
    transcription_enabled: bool = False
    transcription_provider: str = "openai"
    transcription_openai_api_key: str = ""
    transcription_openai_base_url: str = "https://api.openai.com/v1"
    transcription_openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    transcription_openai_summary_model: str = "gpt-4.1-nano"
    transcription_openai_language: str = "en"
    transcription_openai_max_files_per_pass: int = 15
    transcription_openai_sleep_seconds: float = 1.0
    transcription_openai_hour_summary_prompt: str = DEFAULT_TRANSCRIPTION_OPENAI_HOUR_SUMMARY_PROMPT
    transcription_openai_day_summary_prompt: str = DEFAULT_TRANSCRIPTION_OPENAI_DAY_SUMMARY_PROMPT

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
        if self.transcription_openai_max_files_per_pass < 1:
            raise ValueError("OpenAI max files per pass must be at least 1.")
        if self.transcription_openai_sleep_seconds < 0:
            raise ValueError("OpenAI sleep seconds must be 0 or greater.")
        return self


class SmbConnectionStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    share_target: str
    message: str


class StorageStatsResponse(BaseModel):
    ok: bool
    local_audio_files: int
    local_total_bytes: int
    smb_enabled: bool
    smb_connected: bool
    smb_audio_files: int
    smb_total_bytes: int
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
    ui_theme: str
    radios: list[SiteRadioSummary] = Field(default_factory=list)
