import os
import signal
import subprocess
import time

from backend.services.audio_device_inventory_service import AudioDeviceInventoryService
from backend.services.recording_configuration_service import RecordingConfigurationService
from backend.services.shared_alsa_input_service import SharedAlsaInputService


class LiveAudioSourceService:
    def __init__(self) -> None:
        self.configuration_service = RecordingConfigurationService()
        self.audio_device_inventory_service = AudioDeviceInventoryService()
        self.shared_input_service = SharedAlsaInputService()
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.process_settings: dict[str, tuple[str, float, str]] = {}
        self.unavailable_reasons: dict[str, str] = {}

    def _target_icecast_url(self, mount_name: str) -> str:
        password = os.getenv("ICECAST_SOURCE_PASSWORD", "change-me-source")
        host = os.getenv("ICECAST_SERVICE_HOST", "hamvox-icecast")
        port = os.getenv("ICECAST_SERVICE_PORT", "8000")
        return f"icecast://source:{password}@{host}:{port}/{mount_name.lstrip('/')}"

    def _spawn_process(self, radio_profile) -> subprocess.Popen[str]:
        normalized_device_name = self.shared_input_service.ensure_shared_input(radio_profile.audio_device_name)
        audio_gain_db = float(getattr(radio_profile, "audio_gain_db", 0.0) or 0.0)
        audio_filter = "aresample=async=1:first_pts=0"
        if audio_gain_db != 0.0:
            audio_filter = f"volume={audio_gain_db:.1f}dB,{audio_filter}"
        ffmpeg_command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-thread_queue_size",
            "1024",
            "-fflags",
            "+genpts",
            "-use_wallclock_as_timestamps",
            "1",
            "-f",
            "alsa",
            "-channels",
            "1",
            "-sample_rate",
            "48000",
            "-i",
            normalized_device_name,
            "-af",
            audio_filter,
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-content_type",
            "audio/mpeg",
            "-f",
            "mp3",
            self._target_icecast_url(radio_profile.stream_mount),
        ]
        return subprocess.Popen(ffmpeg_command)

    def _stop_process(self, radio_id: str) -> None:
        process = self.processes.get(radio_id)
        if process is None:
            return
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.processes.pop(radio_id, None)
        self.process_settings.pop(radio_id, None)

    def _device_unavailable_reason(self, radio_profile) -> str | None:
        device_name = (radio_profile.audio_device_name or "").strip()
        if not device_name:
            return "no capture device selected"
        if not self.audio_device_inventory_service.has_capture_device(device_name):
            return f"capture device '{device_name}' is not available"
        return None

    def _set_unavailable_reason(self, radio_profile, reason: str) -> None:
        previous_reason = self.unavailable_reasons.get(radio_profile.id)
        if previous_reason == reason:
            return
        print(f"Live source [{radio_profile.name}]: {reason}; waiting for configuration.")
        self.unavailable_reasons[radio_profile.id] = reason

    def _clear_unavailable_reason(self, radio_profile) -> None:
        if self.unavailable_reasons.pop(radio_profile.id, None) is not None:
            print(f"Live source [{radio_profile.name}]: capture device ready, starting stream.")

    def run_forever(self) -> None:
        while True:
            radios = {radio.id: radio for radio in self.configuration_service.get_radio_profiles(enabled_only=True)}

            for radio_id in list(self.processes):
                if radio_id not in radios:
                    self._stop_process(radio_id)

            for radio_id, radio in radios.items():
                unavailable_reason = self._device_unavailable_reason(radio)
                if unavailable_reason is not None:
                    self._stop_process(radio_id)
                    self._set_unavailable_reason(radio, unavailable_reason)
                    continue

                self._clear_unavailable_reason(radio)
                expected = (radio.audio_device_name, float(radio.audio_gain_db), radio.stream_mount)
                current_process = self.processes.get(radio_id)
                if current_process is None or current_process.poll() is not None:
                    self._stop_process(radio_id)
                    self.processes[radio_id] = self._spawn_process(radio)
                    self.process_settings[radio_id] = expected
                elif self.process_settings.get(radio_id) != expected:
                    self._stop_process(radio_id)
                    self.processes[radio_id] = self._spawn_process(radio)
                    self.process_settings[radio_id] = expected

            time.sleep(3)


def main() -> None:
    LiveAudioSourceService().run_forever()


if __name__ == "__main__":
    main()
