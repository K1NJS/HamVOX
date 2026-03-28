import math
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.services.audio_device_inventory_service import AudioDeviceInventoryService
from backend.services.discord_webhook_service import DiscordWebhookService
from backend.services.recording_configuration_service import RecordingConfigurationService
from backend.services.shared_alsa_input_service import SharedAlsaInputService
from backend.services.smb_backup_service import SmbBackupService


class AudioCaptureRecordingService:
    def __init__(self) -> None:
        self.configuration_service = RecordingConfigurationService()
        self.audio_device_inventory_service = AudioDeviceInventoryService()
        self.shared_input_service = SharedAlsaInputService()
        self.smb_backup_service = SmbBackupService()
        self.discord_webhook_service = DiscordWebhookService()
        self.archive_root = Path(os.getenv("HAMVOX_ARCHIVE_ROOT", "/recordings/archive"))
        self.work_root = Path(os.getenv("HAMVOX_WORK_ROOT", "/recordings/.radio-recorder-app/work"))
        self.timezone = ZoneInfo(os.getenv("HAMVOX_TIMEZONE", "America/New_York"))
        self.default_capture_pass_timeout_seconds = int(
            os.getenv("HAMVOX_CAPTURE_PASS_TIMEOUT_SECONDS", "30")
        )
        self.worker_controls: dict[str, threading.Event] = {}
        self.worker_threads: dict[str, threading.Thread] = {}
        self.unavailable_reasons: dict[str, str] = {}

    def _safe_radio_name(self, name: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|]+", "", str(name)).strip()
        return cleaned or "Radio"

    def _radio_display_suffix(self, radio_profile) -> str:
        return self._safe_radio_name(getattr(radio_profile, "name", "Radio"))

    def _timestamp_paths(self, timestamp: datetime, radio_profile) -> tuple[Path, str]:
        day_folder = timestamp.strftime("%b").replace(" 0", " ") + str(timestamp.day) + timestamp.strftime("-%Y")
        hour_folder = timestamp.strftime("%I").lstrip("0") + timestamp.strftime("%p")
        base_name = timestamp.strftime("%I").lstrip("0") + timestamp.strftime("_%M%p")
        base_name = f"{base_name} {self._radio_display_suffix(radio_profile)}"
        return self.archive_root / day_folder / hour_folder, base_name

    def _unique_destination(self, destination_dir: Path, base_name: str) -> Path:
        candidate = destination_dir / f"{base_name}.wav"
        if not candidate.exists():
            return candidate
        match = re.match(r"^(.*?)(\s+[^ ](?:.*))$", base_name)
        if match:
            time_part = match.group(1)
            suffix_part = match.group(2)
        else:
            time_part = base_name
            suffix_part = ""
        index = 1
        while True:
            candidate = destination_dir / f"{time_part} ({index}){suffix_part}.wav"
            if not candidate.exists():
                return candidate
            index += 1

    def _clip_duration_seconds(self, file_path: Path) -> float:
        result = subprocess.run(
            ["soxi", "-D", str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return float((result.stdout or "0").strip() or "0")
        except ValueError:
            return 0.0

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
        print(f"Recorder [{radio_profile.name}]: {reason}; waiting for configuration.")
        self.unavailable_reasons[radio_profile.id] = reason

    def _clear_unavailable_reason(self, radio_profile) -> None:
        if self.unavailable_reasons.pop(radio_profile.id, None) is not None:
            print(f"Recorder [{radio_profile.name}]: capture device ready, resuming recording.")

    def _record_once(self, configuration, radio_profile) -> None:
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.archive_root.mkdir(parents=True, exist_ok=True)
        input_name = self.shared_input_service.ensure_shared_input(radio_profile.audio_device_name)
        temp_file = self.work_root / f"vox_{radio_profile.id}_{int(time.time())}.wav"
        capture_pass_timeout_seconds = int(
            max(
                getattr(radio_profile, "max_clip_seconds", self.default_capture_pass_timeout_seconds),
                getattr(radio_profile, "min_clip_seconds", 1.0),
            )
        )

        sox_command = [
            "sox",
            "-t",
            "alsa",
            "-c",
            "1",
            "-r",
            "48000",
            "-b",
            "16",
            input_name,
            str(temp_file),
        ]

        if float(getattr(radio_profile, "audio_gain_db", 0.0) or 0.0) != 0.0:
            sox_command.extend(["gain", f"{float(radio_profile.audio_gain_db):.1f}"])

        sox_command.extend(
            [
                "silence",
                "1",
                "0.1",
                radio_profile.vox_start.split()[-1],
                "1",
                f"{float(getattr(radio_profile, 'stop_after_silence_seconds', 1.5)):.1f}",
                radio_profile.vox_stop.split()[-1],
            ]
        )

        process = subprocess.Popen(sox_command)
        timed_out = False
        try:
            process.wait(timeout=capture_pass_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            print(
                f"Recorder [{radio_profile.name}]: max clip length reached after "
                f"{capture_pass_timeout_seconds}s, flushing clip and reloading settings."
            )
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        if not temp_file.exists():
            print(f"Recorder [{radio_profile.name}]: no clip created.")
            return

        clip_length = self._clip_duration_seconds(temp_file)
        if timed_out and clip_length <= 0:
            print(
                f"Recorder [{radio_profile.name}]: timed out clip {temp_file.name} did not finalize cleanly."
            )
            temp_file.unlink(missing_ok=True)
            return
        if clip_length < radio_profile.min_clip_seconds:
            print(
                f"Recorder [{radio_profile.name}]: discarded short clip {temp_file.name} "
                f"({clip_length:.2f}s < {radio_profile.min_clip_seconds:.2f}s)."
            )
            temp_file.unlink(missing_ok=True)
            return

        ended_at = datetime.fromtimestamp(temp_file.stat().st_mtime, self.timezone)
        destination_dir, base_name = self._timestamp_paths(ended_at, radio_profile)
        is_new_hour = not destination_dir.exists() or not any(destination_dir.glob("*.wav"))
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = self._unique_destination(destination_dir, base_name)
        shutil.move(str(temp_file), str(destination))
        print(f"Recorder [{radio_profile.name}]: saved clip to {destination}")

        relative_path = destination.relative_to(self.archive_root)
        if configuration.smb_backup_enabled:
            success, message = self.smb_backup_service.upload_file(
                destination,
                relative_path,
                configuration,
            )
            if success:
                print(f"Recorder [{radio_profile.name}]: {message}")
            else:
                print(f"Recorder [{radio_profile.name}]: SMB backup failed: {message}")

        alert_mode = (getattr(configuration, "discord_alert_mode", "per_clip") or "per_clip").strip()
        should_alert = configuration.discord_webhook_enabled and (
            alert_mode == "per_clip" or (alert_mode == "new_hour" and is_new_hour)
        )
        if should_alert:
            alert_reason = "new_hour" if alert_mode == "new_hour" and is_new_hour else "per_clip"
            success, message = self.discord_webhook_service.send_recording_alert(
                configuration,
                relative_path,
                clip_length,
                alert_reason,
                radio_profile.name,
            )
            print(f"Recorder [{radio_profile.name}]: {message}")

    def _run_radio_loop(self, radio_id: str, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            configuration = self.configuration_service.get_configuration()
            radio_profile = self.configuration_service.get_radio_profile(radio_id)
            if radio_profile is None or not radio_profile.enabled:
                break
            unavailable_reason = self._device_unavailable_reason(radio_profile)
            if unavailable_reason is not None:
                self._set_unavailable_reason(radio_profile, unavailable_reason)
                if stop_event.wait(3):
                    break
                continue
            self._clear_unavailable_reason(radio_profile)
            self._record_once(configuration, radio_profile)
            if stop_event.wait(1):
                break

    def run_forever(self) -> None:
        while True:
            active_profiles = {radio.id: radio for radio in self.configuration_service.get_radio_profiles(enabled_only=True)}

            for radio_id in list(self.worker_threads):
                if radio_id not in active_profiles:
                    self.worker_controls[radio_id].set()
                    self.worker_threads[radio_id].join(timeout=1)
                    self.worker_controls.pop(radio_id, None)
                    self.worker_threads.pop(radio_id, None)

            for radio_id in active_profiles:
                thread = self.worker_threads.get(radio_id)
                if thread is None or not thread.is_alive():
                    stop_event = threading.Event()
                    worker = threading.Thread(
                        target=self._run_radio_loop,
                        args=(radio_id, stop_event),
                        daemon=True,
                        name=f"radio-capture-{radio_id}",
                    )
                    self.worker_controls[radio_id] = stop_event
                    self.worker_threads[radio_id] = worker
                    worker.start()

            time.sleep(2)

    def run_threshold_test(self, radio_id: str | None = None, sample_seconds: float = 4.0) -> dict[str, object]:
        radio_profile = (
            self.configuration_service.get_radio_profile(radio_id)
            if radio_id
            else None
        )
        if radio_profile is None:
            radios = self.configuration_service.get_radio_profiles(enabled_only=True)
            radio_profile = radios[0] if radios else None
        if radio_profile is None:
            return {"ok": False, "message": "No enabled radio profile is configured."}
        unavailable_reason = self._device_unavailable_reason(radio_profile)
        if unavailable_reason is not None:
            return {
                "ok": False,
                "message": f"{radio_profile.name}: {unavailable_reason}. Select a valid device first.",
            }

        self.work_root.mkdir(parents=True, exist_ok=True)
        input_name = self.shared_input_service.ensure_shared_input(radio_profile.audio_device_name)
        temp_file = self.work_root / f"threshold_test_{radio_profile.id}_{int(time.time())}.wav"
        capture_command = [
            "sox",
            "-q",
            "-t",
            "alsa",
            "-c",
            "1",
            "-r",
            "48000",
            "-b",
            "16",
            input_name,
            str(temp_file),
            "trim",
            "0",
            f"{sample_seconds:.1f}",
        ]
        if float(getattr(radio_profile, "audio_gain_db", 0.0) or 0.0) != 0.0:
            capture_command.extend(["gain", f"{float(radio_profile.audio_gain_db):.1f}"])

        subprocess.run(capture_command, check=False)
        if not temp_file.exists():
            return {"ok": False, "message": "No audio sample was captured from the selected device."}

        analysis_command = ["sox", str(temp_file), "-n", "stat"]
        result = subprocess.run(analysis_command, capture_output=True, text=True, check=False)
        temp_file.unlink(missing_ok=True)

        if result.returncode not in (0, 2):
            return {"ok": False, "message": "Audio analysis failed."}

        peak_amplitude = None
        rms_amplitude = None
        for line in (result.stderr or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("Maximum amplitude:"):
                try:
                    peak_amplitude = float(stripped.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif stripped.startswith("RMS     amplitude:"):
                try:
                    rms_amplitude = float(stripped.split(":", 1)[1].strip())
                except ValueError:
                    pass

        def amplitude_to_db(value: float | None) -> float | None:
            if value is None or value <= 0:
                return None
            return round(20 * math.log10(value), 1)

        peak_db = amplitude_to_db(peak_amplitude)
        rms_db = amplitude_to_db(rms_amplitude)
        start_db = float(radio_profile.start_threshold_db)
        stop_db = float(radio_profile.stop_threshold_db)
        would_trigger_start = peak_db is not None and peak_db >= start_db

        if peak_db is None:
            message = "No usable signal level was detected in the sample."
        elif would_trigger_start:
            message = (
                f"Peak level {peak_db:.1f} dB should trigger the current start threshold "
                f"of {start_db:.1f} dB for {radio_profile.name}."
            )
        else:
            message = (
                f"Peak level {peak_db:.1f} dB is below the current start threshold "
                f"of {start_db:.1f} dB for {radio_profile.name}."
            )

        return {
            "ok": True,
            "message": message,
            "peak_db": peak_db,
            "rms_db": rms_db,
            "gain_db": float(radio_profile.audio_gain_db),
            "start_threshold_db": start_db,
            "stop_threshold_db": stop_db,
            "stop_after_silence_seconds": float(getattr(radio_profile, "stop_after_silence_seconds", 1.5)),
            "would_trigger_start": would_trigger_start,
        }

    def sample_live_level(self, radio_id: str | None = None, sample_seconds: float = 0.8) -> dict[str, object]:
        payload = self.run_threshold_test(radio_id=radio_id, sample_seconds=sample_seconds)
        if payload.get("ok"):
            radio_profile = (
                self.configuration_service.get_radio_profile(radio_id)
                if radio_id
                else None
            )
            radio_name = getattr(radio_profile, "name", "radio")
            payload["message"] = f"Live level sampled for {radio_name}."
        return payload


def main() -> None:
    AudioCaptureRecordingService().run_forever()


if __name__ == "__main__":
    main()
