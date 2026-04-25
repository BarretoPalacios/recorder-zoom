from __future__ import annotations

from typing import TYPE_CHECKING

from ..config.settings import RecordingSettings
from .dto import RecordingArtifact, StartRecordingResult, StopRecordingResult

if TYPE_CHECKING:
    from ..recorder import FocusRecorder


class RecordingService:
    def start_recording(self, settings: RecordingSettings) -> StartRecordingResult:
        from ..recorder import FocusRecorder

        recorder = FocusRecorder(config=settings)
        recorder.start()
        return StartRecordingResult(recorder=recorder, filename=recorder.filename)

    def stop_capture(self, recorder: FocusRecorder) -> RecordingArtifact:
        return recorder.stop_capture()

    def render_recording(
        self,
        recorder: FocusRecorder,
        artifact: RecordingArtifact,
        *,
        callback_progress=None,
        export_mode="full",
    ) -> StopRecordingResult:
        recorder.render_recording(
            artifact,
            callback_progress=callback_progress,
            export_mode=export_mode,
        )
        return StopRecordingResult(
            full_path=recorder.filename if export_mode in ("full", "both") else "",
            tiktok_path=recorder.filename.replace(".mp4", "_tiktok.mp4") if export_mode in ("tiktok", "both") else "",
        )

    def stop_recording(self, recorder: FocusRecorder, *, callback_progress=None, export_mode="full"):
        artifact = self.stop_capture(recorder)
        return self.render_recording(
            recorder,
            artifact,
            callback_progress=callback_progress,
            export_mode=export_mode,
        )
