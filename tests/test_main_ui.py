from unittest.mock import MagicMock
import focusrecorder.main as main_module
from focusrecorder.main import FocusApp
from focusrecorder.application.dto import StopRecordingResult


def test_get_export_mode_mapping(qtbot):
    app = FocusApp()
    qtbot.addWidget(app)

    app.radio_full.setChecked(True)
    assert app._get_export_mode() == "full"

    app.radio_tiktok.setChecked(True)
    assert app._get_export_mode() == "tiktok"

    app.radio_both.setChecked(True)
    assert app._get_export_mode() == "both"


class DummyRecorder:
    def __init__(self):
        self.is_recording = False
        self.filename = "C:/tmp/video_7.mp4"

class DummyRecordingService:
    def __init__(self):
        self.recorder = None

    def execute(self, settings):
        self.recorder = DummyRecorder()
        self.recorder.is_recording = True
        self.settings = settings
        return MagicMock(recorder=self.recorder, filename="C:/tmp/video_7.mp4")

def test_toggle_start_updates_ui_and_config(monkeypatch, qtbot):
    app = FocusApp()
    qtbot.addWidget(app)
    
    dummy_service = DummyRecordingService()
    app.presenter.start_recording_use_case = dummy_service

    app.zoom_spin.setValue(20)
    app.smooth_slider.setValue(5)
    app.fps_spin.setValue(30)
    app.render_quality_combo.setCurrentIndex(app.render_quality_combo.findData("fast"))

    app.toggle()

    assert app.presenter.recorder == dummy_service.recorder
    assert app.presenter.recorder.is_recording
    import pytest
    assert dummy_service.settings.zoom == pytest.approx(2.0)
    assert dummy_service.settings.suavidad == pytest.approx(0.05)
    assert dummy_service.settings.fps == 30
    assert dummy_service.settings.render_quality == "fast"

    assert app.btn.text() == "DETENER Y PROCESAR"
    assert "Grabando" in app.status.text()
    assert not app.zoom_spin.isEnabled()
    assert not app.smooth_slider.isEnabled()
    assert not app.fps_spin.isEnabled()


def test_on_finished_shows_filenames_and_resets_controls(qtbot):
    app = FocusApp()
    qtbot.addWidget(app)

    app.progress_bar.setVisible(True)
    app._set_controls_enabled(False)

    app.on_finished(StopRecordingResult("C:/tmp/video_1.mp4", "C:/tmp/video_1_tiktok.mp4"))

    status_text = app.status.text()
    assert "video_1.mp4" in status_text
    assert "video_1_tiktok.mp4" in status_text
    assert app.btn.text() == "INICIAR GRABACIÓN"
    assert not app.progress_bar.isVisible()
    assert app.zoom_spin.isEnabled()
    assert app.smooth_slider.isEnabled()
    assert app.fps_spin.isEnabled()


def test_hotkey_pause_changes_status(qtbot):
    app = FocusApp()
    qtbot.addWidget(app)

    app._handle_hotkey_pause_changed(True)
    assert "pausa" in app.status.text().lower()
    assert app.header_badge.text() == "PAUSADO"

    app._handle_hotkey_pause_changed(False)
    assert "grabando" in app.status.text().lower()
    assert app.header_badge.text() == "REC EN CURSO"
