from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..recorder import FocusRecorder
    from ..config.settings import RecordingSettings


@dataclass(frozen=True)
class StartRecordingResult:
    recorder: FocusRecorder
    filename: str


@dataclass(frozen=True)
class RecordingArtifact:
    filename: str
    settings: RecordingSettings
    screen_size: tuple[int, int]
    raw_data: tuple
    mouse_data: tuple
    temp_path: str = ""
    audio_wav: str | None = None


@dataclass(frozen=True)
class StopRecordingResult:
    full_path: str
    tiktok_path: str
