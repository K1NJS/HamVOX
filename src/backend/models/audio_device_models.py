from pydantic import BaseModel


class AudioDeviceSummary(BaseModel):
    card_index: int
    device_index: int
    card_name: str
    device_name: str
    alsa_hardware_name: str


class AudioDeviceInventoryResponse(BaseModel):
    capture_devices: list[AudioDeviceSummary]

