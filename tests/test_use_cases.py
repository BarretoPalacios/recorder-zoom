from unittest.mock import MagicMock

from focusrecorder.application.dto import RecordingArtifact, StartRecordingResult, StopRecordingResult
from focusrecorder.application.use_cases.prepare_recording import PrepareRecordingUseCase
from focusrecorder.application.use_cases.render_recording import RenderRecordingUseCase
from focusrecorder.application.use_cases.start_recording import StartRecordingUseCase
from focusrecorder.application.use_cases.stop_recording import StopRecordingUseCase


def test_start_recording_use_case_delegates_to_service():
    service = MagicMock()
    expected = StartRecordingResult(recorder=MagicMock(), filename="video.mp4")
    service.start_recording.return_value = expected

    use_case = StartRecordingUseCase(recording_service=service)
    settings = MagicMock()

    result = use_case.execute(settings)

    service.start_recording.assert_called_once_with(settings)
    assert result == expected


def test_stop_recording_use_case_delegates_to_service():
    service = MagicMock()
    recorder = MagicMock()
    expected = StopRecordingResult(full_path="video.mp4", tiktok_path="")
    service.stop_recording.return_value = expected

    use_case = StopRecordingUseCase(recording_service=service)

    result = use_case.execute(recorder, callback_progress="progress", export_mode="full")

    service.stop_recording.assert_called_once_with(
        recorder,
        callback_progress="progress",
        export_mode="full",
    )
    assert result == expected


def test_prepare_recording_use_case_delegates_to_service():
    service = MagicMock()
    recorder = MagicMock()
    expected = MagicMock(spec=RecordingArtifact)
    service.stop_capture.return_value = expected

    use_case = PrepareRecordingUseCase(recording_service=service)

    result = use_case.execute(recorder)

    service.stop_capture.assert_called_once_with(recorder)
    assert result == expected


def test_render_recording_use_case_delegates_to_service():
    service = MagicMock()
    recorder = MagicMock()
    artifact = MagicMock(spec=RecordingArtifact)
    expected = StopRecordingResult(full_path="video.mp4", tiktok_path="")
    service.render_recording.return_value = expected

    use_case = RenderRecordingUseCase(recording_service=service)

    result = use_case.execute(recorder, artifact, callback_progress="progress", export_mode="full")

    service.render_recording.assert_called_once_with(
        recorder,
        artifact,
        callback_progress="progress",
        export_mode="full",
    )
    assert result == expected
