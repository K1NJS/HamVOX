import hashlib
import re
import threading
from pathlib import Path


class SharedAlsaInputService:
    ALSA_CONFIG_PATH = Path("/root/.asoundrc")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._aliases: dict[str, tuple[str, str]] = {}

    def _extract_hw_target(self, device_name: str) -> str:
        if device_name.startswith("plughw:"):
            return "hw:" + device_name[len("plughw:"):]
        if device_name.startswith("hw:"):
            return device_name

        match = re.search(r"CARD=([^,]+),DEV=(\d+)", device_name)
        if match:
            return f'hw:CARD={match.group(1)},DEV={match.group(2)}'

        return device_name

    def _alias_names_for(self, hw_target: str) -> tuple[str, str]:
        digest = hashlib.sha1(hw_target.encode("utf-8")).hexdigest()[:10]
        return (f"plug_radio_in_{digest}", f"radio_capture_shared_{digest}")

    def _render_config(self) -> str:
        blocks: list[str] = []
        for hw_target, (pcm_name, raw_name) in sorted(self._aliases.items()):
            blocks.append(
                f'''pcm.{raw_name} {{
  type dsnoop
  ipc_key 5978293
  ipc_key_add_uid false
  slave {{
    pcm "{hw_target}"
    channels 1
    rate 48000
    format S16_LE
  }}
}}

pcm.{pcm_name} {{
  type plug
  slave.pcm "{raw_name}"
}}
'''
            )
        return "\n".join(blocks) + ("\n" if blocks else "")

    def ensure_shared_input(self, device_name: str) -> str:
        hw_target = self._extract_hw_target(device_name)
        with self._lock:
            pcm_name, raw_name = self._aliases.get(hw_target, self._alias_names_for(hw_target))
            self._aliases[hw_target] = (pcm_name, raw_name)
            temp_path = self.ALSA_CONFIG_PATH.with_suffix(".tmp")
            temp_path.write_text(self._render_config())
            temp_path.replace(self.ALSA_CONFIG_PATH)
            return pcm_name
