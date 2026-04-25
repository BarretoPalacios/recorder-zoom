from __future__ import annotations

from typing import TYPE_CHECKING

from ..dto import RecordingArtifact, StopRecordingResult
from ..recording_service import RecordingService

if TYPE_CHECKING:
    from ...recorder import FocusRecorder


class RenderRecordingUseCase:
    def __init__(self, recording_service=None):
        self.recording_service = recording_service or RecordingService()

    def execute(
        self,
        recorder: FocusRecorder,
        artifact: RecordingArtifact,
        *,
        callback_progress=None,
        export_mode="full",
    ) -> StopRecordingResult:
        return self.recording_service.render_recording(
            recorder,
            artifact,
            callback_progress=callback_progress,
            export_mode=export_mode,
        )
