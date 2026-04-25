from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RecordingSettings:
    """Settings for a recording session."""
    zoom: float
    suavidad: float
    fps: int
    output_dir: Path
    custom_name: str = ""
    audio: bool = False
    audio_mode: str = "mic"
    audio_device: int | None = None
    pause_hotkey: str = "f7"
    stop_hotkey: str = "f10"
    quality: str = "high"
    render_quality: str = "normal"


@dataclass(frozen=True)
class UISettings:
    """Settings for the user interface state."""
    export_mode: str  # "full", "tiktok", "both"
    preview_enabled: bool = True


@dataclass(frozen=True)
class UserPreferences:
    """Complete user preferences combining recording and UI settings."""
    recording: RecordingSettings
    ui: UISettings
