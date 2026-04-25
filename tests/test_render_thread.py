from unittest.mock import MagicMock
from focusrecorder.main import RenderThread
from focusrecorder.application.dto import StopRecordingResult


def test_render_thread_full_mode_emits_paths(qtbot):
    presenter = MagicMock()
    presenter.render_prepared_recording.return_value = StopRecordingResult(
        "C:/tmp/res.mp4",
        "",
    )

    thread = RenderThread(presenter, export_mode="full")

    finished_payload = []
    thread.finished.connect(lambda result: finished_payload.append((result.full_path, result.tiktok_path)))

    thread.run()

    assert finished_payload == [("C:/tmp/res.mp4", "")]


def test_render_thread_both_mode_emits_both_paths(qtbot):
    presenter = MagicMock()
    presenter.render_prepared_recording.return_value = StopRecordingResult(
        "C:/tmp/res.mp4",
        "C:/tmp/res_tiktok.mp4",
    )

    thread = RenderThread(presenter, export_mode="both")

    finished_payload = []
    thread.finished.connect(lambda result: finished_payload.append((result.full_path, result.tiktok_path)))

    thread.run()

    assert finished_payload == [("C:/tmp/res.mp4", "C:/tmp/res_tiktok.mp4")]
