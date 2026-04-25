import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FrameSample:
    frame: Any
    mouse_x: int
    mouse_y: int
    is_clicking: bool
    timestamp: float

    def as_tuple(self):
        return (self.frame, self.mouse_x, self.mouse_y, self.is_clicking, self.timestamp)


@dataclass
class RecordingSessionState:
    is_recording: bool = False
    is_paused: bool = False
    is_clicking: bool = False
    start_time: float = 0.0
    stop_time: float = 0.0
    pause_started_at: float = 0.0
    total_paused_time: float = 0.0
    mouse_data: list = field(default_factory=list)  # (mx, my, clicking, ts) — sin frames
    latest_frame: Any = None
    latest_mx: int = 0
    latest_my: int = 0

    def reset(self, start_time: float) -> None:
        self.is_recording = True
        self.is_paused = False
        self.is_clicking = False
        self.start_time = start_time
        self.stop_time = 0.0
        self.pause_started_at = 0.0
        self.total_paused_time = 0.0
        self.mouse_data = []
        self.latest_frame = None
        self.latest_mx = 0
        self.latest_my = 0

    def stop(self, now: float | None = None) -> None:
        self.is_recording = False
        self.is_paused = False
        self.stop_time = now if now is not None else time.perf_counter()

    def pause(self, now: float | None = None) -> None:
        if self.is_recording and not self.is_paused:
            self.is_paused = True
            self.pause_started_at = now if now is not None else time.perf_counter()

    def resume(self, now: float | None = None) -> None:
        if self.is_paused:
            resume_time = now if now is not None else time.perf_counter()
            self.total_paused_time += max(resume_time - self.pause_started_at, 0.0)
            self.pause_started_at = 0.0
            self.is_paused = False

    def elapsed(self, now: float | None = None) -> float:
        current_time = now if now is not None else time.perf_counter()
        if not self.is_recording and self.stop_time:
            current_time = min(current_time, self.stop_time)
        paused_time = self.total_paused_time
        if self.is_paused and self.pause_started_at:
            paused_time += max(current_time - self.pause_started_at, 0.0)
        return max(current_time - self.start_time - paused_time, 0.0)

    def set_clicking(self, pressed: bool) -> None:
        self.is_clicking = pressed

    def append_sample(self, sample: FrameSample) -> None:
        self.mouse_data.append(
            (sample.mouse_x, sample.mouse_y, sample.is_clicking, sample.timestamp)
        )
        self.latest_frame = sample.frame
        self.latest_mx = sample.mouse_x
        self.latest_my = sample.mouse_y
