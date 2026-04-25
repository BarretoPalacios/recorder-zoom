import os
import numpy as np
import cv2
from unittest.mock import MagicMock

from focusrecorder.recorder import FocusRecorder
import focusrecorder.recorder as recorder_module
import focusrecorder.utils.video_utils as video_utils_module
from focusrecorder.config.settings import RecordingSettings

def test_recorder_full_rendering_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    
    settings = RecordingSettings(
        zoom=2.0, suavidad=0.5, fps=10, 
        output_dir=tmp_path / "Desktop" / "videos"
    )
    rec = FocusRecorder(config=settings)
    rec.capture_backend = MagicMock()
    
    def fake_reencode(path):
        pass

    monkeypatch.setattr(video_utils_module, "reencode_to_h264", fake_reencode)

    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    rec.raw_data = [
        (blank_frame.copy(), 320, 240, False, 0.0),
        (blank_frame.copy(), 320, 240, True, 1.0),
        (blank_frame.copy(), 100, 100, False, 2.0),
    ]
    
    writer_calls = []
    class FakeVideoWriter:
        def __init__(self, filename, fourcc, fps, frameSize):
            self.filename = filename
            writer_calls.append(("init", filename, fps, frameSize))
        def write(self, frame):
            writer_calls.append(("write", id(self)))
        def release(self):
            writer_calls.append(("release", id(self)))
            with open(self.filename, 'w') as f:
                f.write("mockvideo")

    from focusrecorder.infrastructure.rendering.adaptive_renderer import AdaptiveVideoRenderer
    monkeypatch.setattr(AdaptiveVideoRenderer, "_create_writer", staticmethod(lambda filename, fps, frame_size: FakeVideoWriter(filename, "mp4v", fps, frame_size)))

    emitted_progress = []
    
    rec._render_adaptive_video(callback_progress=emitted_progress.append, export_mode="both")
    
    assert len(writer_calls) > 0
    assert len(emitted_progress) > 0
    assert emitted_progress[-1] == 100


def test_recorder_full_various_modes(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    
    rec = FocusRecorder(config={"zoom": 2.0, "suavidad": 0.5, "fps": 10})
    rec.capture_backend = MagicMock()
    
    monkeypatch.setattr(video_utils_module, "reencode_to_h264", lambda x: None)
    
    class MockVideoWriter:
        def __init__(self, filename, fourcc, fps, frameSize):
            self.filename = filename
            import os
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'wb') as f:
                f.write(b"mockvideo")
        def write(self, frame):
            pass
        def release(self):
            pass
    
    from focusrecorder.infrastructure.rendering.adaptive_renderer import AdaptiveVideoRenderer
    monkeypatch.setattr(AdaptiveVideoRenderer, "_create_writer", staticmethod(lambda filename, fps, frame_size: MockVideoWriter(filename, "mp4v", fps, frame_size)))
    
    rec.raw_data = []
    rec._render_adaptive_video(None, "both")
    
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    rec.raw_data = [
        (blank_frame.copy(), 320, 240, False, 0.0),
        (blank_frame.copy(), 320, 240, True, 1.0)
    ]

    rec._render_adaptive_video(None, "full")
    rec._render_adaptive_video(None, "tiktok")


def test_recorder_reencode_fails_gracefully(monkeypatch, tmp_path):
    """Test that reencode function from video_utils is called during rendering"""
    import subprocess
    
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    rec = FocusRecorder(config={"zoom": 2.0, "suavidad": 0.5, "fps": 10})
    rec.capture_backend = MagicMock()
    
    mock_subprocess_run = MagicMock()
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    
    mock_os_exists = MagicMock(return_value=False)
    mock_os_getsize = MagicMock(return_value=100)
    monkeypatch.setattr(os.path, "exists", mock_os_exists)
    monkeypatch.setattr(os.path, "getsize", mock_os_getsize)
    
    from focusrecorder.utils.video_utils import reencode_to_h264
    reencode_to_h264("fake_path.mp4")
    
    assert mock_subprocess_run.called


def test_recorder_os_logic(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    rec = FocusRecorder(config={"zoom": 2.0, "suavidad": 0.5, "fps": 10})
    assert rec.settings.zoom == 2.0


def test_recorder_stop_no_listener(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    rec = FocusRecorder(config={"zoom": 2.0, "suavidad": 0.5, "fps": 10})
    rec.is_recording = True
    rec.thread = MagicMock()
    rec._render_adaptive_video = MagicMock()
    rec.capture_backend = MagicMock()
    
    rec.stop(None, "full")
    rec._render_adaptive_video.assert_called_once()

def test_renderer_synchronizes_low_framerate_to_target_fps(monkeypatch):
    from focusrecorder.infrastructure.rendering.adaptive_renderer import AdaptiveVideoRenderer
    from focusrecorder.config.settings import RecordingSettings
    import focusrecorder.infrastructure.rendering.adaptive_renderer as renderer_module
    
    written_frames = []
    class MockVideoWriter:
        def __init__(self, filename, fourcc, fps, frameSize): pass
        def write(self, frame): written_frames.append(frame)
        def release(self): pass
        
    monkeypatch.setattr(AdaptiveVideoRenderer, "_create_writer", staticmethod(lambda filename, fps, frame_size: MockVideoWriter(filename, "mp4v", fps, frame_size)))
    monkeypatch.setattr(renderer_module, "reencode_to_h264", lambda x: None)
    
    renderer = AdaptiveVideoRenderer()
    settings = RecordingSettings(fps=30, zoom=2.0, suavidad=0.5, output_dir=".")
    
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    raw_data = [
        (blank_frame, 320, 240, False, 0.0),
        (blank_frame, 320, 240, True, 1.0),
        (blank_frame, 100, 100, False, 2.0),
    ]
    
    renderer.render(
        raw_data=raw_data,
        settings=settings,
        screen_size=(640, 480),
        output_filename="dummy.mp4",
        export_mode="full"
    )
    
    assert len(written_frames) == 60, f"Se esperaban 60 frames, se obtuvieron {len(written_frames)}"


def test_renderer_from_file_synchronizes_low_framerate_to_target_fps(monkeypatch):
    from focusrecorder.infrastructure.rendering.adaptive_renderer import AdaptiveVideoRenderer
    from focusrecorder.config.settings import RecordingSettings
    import focusrecorder.infrastructure.rendering.adaptive_renderer as renderer_module
    
    written_frames = []
    class MockVideoWriter:
        def __init__(self, filename, fourcc, fps, frameSize): pass
        def write(self, frame): written_frames.append(frame)
        def release(self): pass

    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    class MockVideoCapture:
        def __init__(self, path):
            self.frames = [blank_frame.copy(), blank_frame.copy(), blank_frame.copy()]
            self.idx = 0
        def read(self):
            if self.idx < len(self.frames):
                frame = self.frames[self.idx]
                self.idx += 1
                return True, frame
            return False, None
        def isOpened(self): return True
        def release(self): pass

    monkeypatch.setattr(AdaptiveVideoRenderer, "_create_writer", staticmethod(lambda filename, fps, frame_size: MockVideoWriter(filename, "mp4v", fps, frame_size)))
    monkeypatch.setattr(cv2, "VideoCapture", MockVideoCapture)
    monkeypatch.setattr(renderer_module, "reencode_to_h264", lambda x: None)
    
    renderer = AdaptiveVideoRenderer()
    settings = RecordingSettings(fps=30, zoom=2.0, suavidad=0.5, output_dir=".")
    
    mouse_data = [
        (320, 240, False, 0.0),
        (320, 240, True, 1.25),
        (100, 100, False, 2.5),
    ]
    
    renderer.render_from_file(
        temp_path="dummy.avi",
        mouse_data=mouse_data,
        settings=settings,
        screen_size=(640, 480),
        output_filename="dummy.mp4",
        export_mode="full"
    )
    
    assert len(written_frames) == 75, f"Se esperaban 75 frames, se obtuvieron {len(written_frames)}"


def test_create_writer_falls_back_when_ffmpeg_encoder_fails(monkeypatch):
    from focusrecorder.infrastructure.rendering import adaptive_renderer as renderer_module

    attempts = []

    class FailingFFmpegWriter:
        def __init__(self, filename, fps, frame_size, encoder):
            attempts.append(encoder)
            if encoder != "libx264":
                raise renderer_module.FFmpegWriterError("encoder no disponible")
            self.encoder = encoder

    class FakeCvWriter:
        def __init__(self, filename, fourcc, fps, frame_size):
            self.filename = filename

    monkeypatch.setattr(renderer_module, "FFmpegVideoWriter", FailingFFmpegWriter)
    monkeypatch.setattr(renderer_module, "get_candidate_video_encoders", lambda: ["h264_nvenc", "h264_qsv", "libx264"])
    monkeypatch.setattr(renderer_module, "can_encode_with_ffmpeg", lambda encoder, width, height, fps: True)
    monkeypatch.setattr(cv2, "VideoWriter", FakeCvWriter)

    writer = renderer_module.AdaptiveVideoRenderer._create_writer("out.mp4", 60, (1920, 1080))

    assert isinstance(writer, FailingFFmpegWriter)
    assert attempts == ["h264_nvenc", "h264_qsv", "libx264"]


def test_create_writer_skips_unavailable_ffmpeg_encoders(monkeypatch):
    from focusrecorder.infrastructure.rendering import adaptive_renderer as renderer_module

    attempts = []

    class FakeFFmpegWriter:
        def __init__(self, filename, fps, frame_size, encoder):
            attempts.append(encoder)
            self.encoder = encoder

    monkeypatch.setattr(renderer_module, "FFmpegVideoWriter", FakeFFmpegWriter)
    monkeypatch.setattr(renderer_module, "get_candidate_video_encoders", lambda: ["h264_nvenc", "libx264"])
    monkeypatch.setattr(renderer_module, "can_encode_with_ffmpeg", lambda encoder, width, height, fps: encoder == "libx264")

    writer = renderer_module.AdaptiveVideoRenderer._create_writer("out.mp4", 60, (1920, 1080))

    assert isinstance(writer, FakeFFmpegWriter)
    assert attempts == ["libx264"]
