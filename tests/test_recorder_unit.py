from pathlib import Path
from unittest.mock import MagicMock

import focusrecorder.recorder as recorder_module
import focusrecorder.config.config as config_module
from focusrecorder.recorder import FocusRecorder
from focusrecorder.config.settings import RecordingSettings

def make_recorder(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder_module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(config_module.Path, "home", lambda: tmp_path)
    
    settings = RecordingSettings(
        zoom=1.8,
        suavidad=0.05,
        fps=30,
        output_dir=tmp_path / "Desktop" / "videos"
    )
    return FocusRecorder(config=settings)


def test_get_video_directory_uses_user_home(monkeypatch, tmp_path):
    rec = make_recorder(monkeypatch, tmp_path)
    assert rec.output_dir == str(tmp_path / "Desktop" / "videos")


def test_get_next_filename_increments_index(monkeypatch, tmp_path):
    video_dir = tmp_path / "Desktop" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    rec = make_recorder(monkeypatch, tmp_path)
    filename = Path(rec.filename).name
    assert filename.startswith("video_")
    assert filename.endswith(".mp4")


def test_get_next_filename_without_name_is_unique(tmp_path):
    from focusrecorder.infrastructure.filesystem.file_naming import get_next_filename

    first = Path(get_next_filename(tmp_path))
    first.write_bytes(b"old")
    second = Path(get_next_filename(tmp_path))

    assert first.name != second.name


def test_reencode_h264_replaces_input_file(monkeypatch, tmp_path):
    """Test that reencode_to_h264 from video_utils works correctly"""
    import subprocess
    import imageio_ffmpeg
    
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"old")

    monkeypatch.setattr(imageio_ffmpeg, "get_ffmpeg_exe", lambda: "ffmpeg-bin")
    mock_subprocess_run = MagicMock()
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    
    from focusrecorder.utils.video_utils import reencode_to_h264
    reencode_to_h264(str(source))

    assert mock_subprocess_run.called


def test_render_adaptive_video_no_data_returns_without_progress(monkeypatch, tmp_path):
    rec = make_recorder(monkeypatch, tmp_path)
    rec.raw_data = []

    progress = []
    rec._render_adaptive_video(callback_progress=progress.append, export_mode="full")

    assert progress == []


def test_build_h264_args_prefers_expected_format(monkeypatch):
    from focusrecorder.infrastructure.encoding import h264_encoder

    monkeypatch.setattr(h264_encoder, "_ffmpeg_version", lambda: (6, 0))

    assert "h264_nvenc" in h264_encoder.build_h264_ffmpeg_args("h264_nvenc")
    assert "p4" in h264_encoder.build_h264_ffmpeg_args("h264_nvenc")
    assert "libx264" in h264_encoder.build_h264_ffmpeg_args("libx264")


def test_get_candidate_video_encoders_always_falls_back_to_libx264(monkeypatch):
    from focusrecorder.infrastructure.encoding import h264_encoder

    h264_encoder._available_encoders.cache_clear()
    monkeypatch.setattr(h264_encoder, "_available_encoders", lambda: {"h264_nvenc"})

    assert h264_encoder.get_candidate_video_encoders() == ["h264_nvenc", "libx264"]


def test_build_h264_args_uses_legacy_nvenc_preset_for_old_ffmpeg(monkeypatch):
    from focusrecorder.infrastructure.encoding import h264_encoder

    h264_encoder._ffmpeg_version.cache_clear()
    monkeypatch.setattr(h264_encoder, "_ffmpeg_version", lambda: (4, 2, 2))

    args = h264_encoder.build_h264_ffmpeg_args("h264_nvenc")

    assert "fast" in args
    assert "p4" not in args


def test_toggle_pause_updates_session_and_callback(monkeypatch, tmp_path):
    rec = make_recorder(monkeypatch, tmp_path)
    rec.session.reset(10.0)

    states = []
    rec.on_pause_toggled = states.append

    assert rec.toggle_pause() is True
    assert rec.is_paused is True

    assert rec.toggle_pause() is False
    assert rec.is_paused is False
    assert states == [True, False]


def test_request_stop_uses_callback_only_while_recording(monkeypatch, tmp_path):
    rec = make_recorder(monkeypatch, tmp_path)
    signals = []
    rec.on_stop_requested = lambda: signals.append("stop")

    rec.request_stop()
    assert signals == []

    rec.session.reset(0.0)
    rec.request_stop()
    assert signals == ["stop"]
