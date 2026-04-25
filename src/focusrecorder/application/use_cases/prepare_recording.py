from __future__ import annotations

from typing import TYPE_CHECKING

from ..dto import RecordingArtifact
from ..recording_service import RecordingService

if TYPE_CHECKING:
    from ...recorder import FocusRecorder


class PrepareRecordingUseCase:
    def __init__(self, recording_service=None):
        self.recording_service = recording_service or RecordingService()

    def execute(self, recorder: FocusRecorder) -> RecordingArtifact:
        return self.recording_service.stop_capture(recorder)
