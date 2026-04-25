import sys
from unittest.mock import patch, MagicMock

import PyQt6.QtWidgets as QtWidgets
import focusrecorder.main as main_module
from focusrecorder.application.dto import StopRecordingResult
from focusrecorder.presentation.qt import main_window as main_window_module


def test_main_run_function():
    with patch("focusrecorder.main.QApplication") as mock_qapp, \
         patch("focusrecorder.main.FocusApp") as mock_app, \
         patch("sys.exit") as mock_exit:
        
        mock_instance = MagicMock()
        mock_app.return_value = mock_instance
        
        main_module.run()
        
        mock_qapp.assert_called_once()
        mock_app.assert_called_once()
        mock_instance.show.assert_called_once()
        mock_exit.assert_called_once()


def test_main_toggle_stops_recording_and_renders(qtbot):
    app = main_module.FocusApp()
    qtbot.addWidget(app)

    app.presenter.recorder = MagicMock()
    app.presenter.recorder.is_recording = True
    
    app.radio_tiktok.setChecked(True)

    with patch.object(main_window_module, "RenderThread") as mock_thread_class:
        mock_thread_instance = MagicMock()
        mock_thread_class.return_value = mock_thread_instance
        
        app.toggle()

        assert not app.btn.isEnabled()
        mock_thread_class.assert_called_once_with(app.presenter, export_mode="tiktok")
        mock_thread_instance.start.assert_called_once()
        assert "TikTok" in app.status.text()
    
    app.on_finished(StopRecordingResult("", ""))
    assert "GRAB" in app.btn.text().upper()


def test_main_toggle_starts_recording(qtbot):
    app = main_module.FocusApp()
    qtbot.addWidget(app)
    
    app.presenter.recorder = None
    
    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.recorder = MagicMock()
    mock_result.filename = "test_video.mp4"
    mock_service.execute.return_value = mock_result
    
    app.presenter.start_recording_use_case = mock_service
    
    app.toggle()
    
    mock_service.execute.assert_called_once()
    assert "DETENER" in app.btn.text()


def test_main_render_thread():
    mock_presenter = MagicMock()
    mock_presenter.render_prepared_recording.return_value = StopRecordingResult(
        "test.mp4",
        "",
    )

    thread = main_module.RenderThread(mock_presenter, export_mode="full")
    thread.progress = MagicMock()
    thread.finished = MagicMock()

    thread.run()
    mock_presenter.render_prepared_recording.assert_called_once()
    thread.finished.emit.assert_called_with(StopRecordingResult("test.mp4", ""))


def test_main_on_finished_with_paths(qtbot):
    app = main_module.FocusApp()
    qtbot.addWidget(app)
    
    app.on_finished(StopRecordingResult("/path/to/full_video.mp4", "/path/to/tiktok_video.mp4"))
    
    assert "full_video.mp4" in app.status.text()
    assert "tiktok_video.mp4" in app.status.text()
