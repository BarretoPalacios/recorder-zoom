import time
import pytest
from unittest.mock import MagicMock
import numpy as np

import focusrecorder.recorder as recorder_module
from focusrecorder.recorder import FocusRecorder


def test_recorder_start_and_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    
    rec = FocusRecorder(config={"zoom": 2.0, "suavidad": 0.5, "fps": 30})
    rec.capture_backend = MagicMock()

    mock_mouse_provider = MagicMock()
    rec.mouse_provider = mock_mouse_provider

    monkeypatch.setattr(rec, "_render_adaptive_video", lambda *args, **kwargs: None)
    monkeypatch.setattr(rec, "_record_loop", lambda: None)
    
    rec.start()
    assert rec.is_recording
    mock_mouse_provider.start_listener.assert_called_once()

    rec._on_click(10, 10, None, True)
    assert rec.is_clicking is True
    rec._on_click(10, 10, None, False)
    assert rec.is_clicking is False

    rec.stop()
    assert not rec.is_recording
    mock_mouse_provider.stop_listener.assert_called_once()



def test_record_loop_windows_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    
    rec = FocusRecorder(config={})
    rec.is_windows = True
    rec.start_time = time.perf_counter()
    rec.is_recording = True
    
    mock_backend = MagicMock()
    frame_return_count = [0]
    def get_frame():
        frame_return_count[0] += 1
        if frame_return_count[0] > 2:
            rec.is_recording = False
            return None
        return np.zeros((480, 640, 3), dtype=np.uint8)
        
    mock_backend.capture_frame.side_effect = get_frame
    rec.capture_backend = mock_backend
    rec.mouse_provider = MagicMock()
    rec.mouse_provider.get_position.return_value = (0, 0)
    
    rec._record_loop()

    assert len(rec.session.mouse_data) > 0
    assert mock_backend.start.called
    assert mock_backend.stop.called


def test_record_loop_linux_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    
    rec = FocusRecorder(config={})
    rec.is_windows = False
    rec.start_time = time.perf_counter()
    rec.is_recording = True
    
    mock_backend = MagicMock()
    def get_frame():
        rec.is_recording = False
        return np.zeros((100, 100, 3), dtype=np.uint8)
            
    mock_backend.capture_frame.side_effect = get_frame
    rec.capture_backend = mock_backend
    rec.mouse_provider = MagicMock()
    rec.mouse_provider.get_position.return_value = (0, 0)
    monkeypatch.setattr(time, "sleep", lambda x: None)

    rec._record_loop()

    assert len(rec.session.mouse_data) == 1


def test_paused_session_does_not_capture_new_frames(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)

    rec = FocusRecorder(config={})
    rec.start_time = time.perf_counter()
    rec.is_recording = True
    rec.session.pause(now=rec.start_time)

    mock_backend = MagicMock()
    mock_backend.capture_frame.side_effect = AssertionError("No deberia capturar en pausa")
    rec.capture_backend = mock_backend
    rec.mouse_provider = MagicMock()

    calls = {"count": 0}

    def fake_sleep(_):
        calls["count"] += 1
        if calls["count"] >= 2:
            rec.is_recording = False

    monkeypatch.setattr(time, "sleep", fake_sleep)
    rec._record_loop()

    assert mock_backend.start.called
    assert mock_backend.stop.called
    assert len(rec.session.mouse_data) == 0
