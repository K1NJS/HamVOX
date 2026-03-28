import json
import os
from pathlib import Path
from typing import Any


class ApplicationSettingsStore:
    def __init__(self) -> None:
        self.settings_path = Path(
            os.getenv(
                "HAMVOX_SETTINGS_PATH",
                "/recordings/.radio-recorder-app/application-settings.json",
            )
        )

    def load(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return {}

        try:
            return json.loads(self.settings_path.read_text())
        except json.JSONDecodeError:
            return {}

    def save(self, payload: dict[str, Any]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
