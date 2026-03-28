import re
import subprocess

from backend.models.audio_device_models import (
    AudioDeviceInventoryResponse,
    AudioDeviceSummary,
)


class AudioDeviceInventoryService:
    def list_capture_devices(self) -> AudioDeviceInventoryResponse:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )

        devices: list[AudioDeviceSummary] = []
        pattern = re.compile(
            r"card (?P<card_index>\d+): (?P<card_short>\S+) \[(?P<card_name>.+?)\], "
            r"device (?P<device_index>\d+): (?P<device_name>.+?) \[(?P<device_label>.+?)\]"
        )

        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            card_short = match.group("card_short")
            devices.append(
                AudioDeviceSummary(
                    card_index=int(match.group("card_index")),
                    device_index=int(match.group("device_index")),
                    card_name=match.group("card_name"),
                    device_name=match.group("device_name"),
                    alsa_hardware_name=f"plughw:CARD={card_short},DEV={match.group('device_index')}",
                )
            )

        return AudioDeviceInventoryResponse(capture_devices=devices)

    def available_capture_device_names(self) -> set[str]:
        inventory = self.list_capture_devices()
        return {device.alsa_hardware_name for device in inventory.capture_devices}

    def has_capture_device(self, device_name: str) -> bool:
        normalized = (device_name or "").strip()
        if not normalized:
            return False
        return normalized in self.available_capture_device_names()
