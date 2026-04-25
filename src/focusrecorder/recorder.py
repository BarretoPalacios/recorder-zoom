import threading
import time
import os
import queue
from pathlib import Path
import cv2
from .config.config import coerce_recording_settings
from .app.factories.capture_backend_factory import create_capture_backend
from .app.factories.mouse_provider_factory import create_mouse_provider
from .app.factories.renderer_factory import create_renderer
from .application.errors import RecordingEnvironmentError
from .application.dto import RecordingArtifact
from .domain.ports.capture_backend import CaptureBackend
from .domain.ports.mouse_provider import MouseProvider
from .domain.models.recording_session import FrameSample, RecordingSessionState
from .config.settings import RecordingSettings
from .infrastructure.filesystem.file_naming import get_next_filename
from .infrastructure.audio.sounddevice_audio import BOTH_AUDIO_MODE, CombinedAudioRecorder, HAS_AUDIO, SounddeviceAudioRecorder
from .infrastructure.capture.windows_cursor import WindowsCursorOverlay

import platform
IS_WINDOWS = platform.system() == "Windows"



class FocusRecorder:
    def __init__(self, config=None):
        self.is_windows = IS_WINDOWS
        self.settings = coerce_recording_settings(config)
        self.capture_backend = self._build_capture_backend()
        self.mouse_provider = self._build_mouse_provider()
        self.renderer = self._build_renderer()
        self.session = RecordingSessionState()
        self.sw = None
        self.sh = None

        self.output_dir = self._get_video_directory()
        os.makedirs(self.output_dir, exist_ok=True)
        self.filename = get_next_filename(
            self.output_dir, prefix="video", custom_name=self.settings.custom_name
        )

        self._audio_recorder = None
        if self.settings.audio and HAS_AUDIO:
            if self.settings.audio_mode == BOTH_AUDIO_MODE:
                self._audio_recorder = CombinedAudioRecorder(system_device=self.settings.audio_device)
            else:
                self._audio_recorder = SounddeviceAudioRecorder(
                    device=self.settings.audio_device,
                    mode=self.settings.audio_mode,
                )

        self._temp_writer = None
        self._temp_path = ""
        self._writer_queue = None
        self._writer_thread = None
        self._writer_error = None
        self._injected_raw_data = []  # solo usado por tests
        self._keyboard_listener = None
        self._keyboard_module = None
        self._hotkeys_down = set()
        self.on_pause_toggled = None
        self.on_stop_requested = None
        self._cursor_overlay = self._build_cursor_overlay()

    def _get_video_directory(self):
        """
        Obtiene la carpeta de videos apropiada según la plataforma.
        Guarda en una carpeta compartida del workspace para que los archivos sean
        accesibles también desde Windows cuando se trabaja sobre /d.
        """
        return str(self.settings.output_dir)

    def _on_click(self, x, y, button, pressed):
        self.session.set_clicking(pressed)

    def _build_capture_backend(self) -> CaptureBackend:
        return create_capture_backend(is_windows=self.is_windows)

    def _build_mouse_provider(self) -> MouseProvider:
        return create_mouse_provider()

    def _build_renderer(self):
        return create_renderer()

    def _build_cursor_overlay(self):
        if not self.is_windows:
            return None
        if type(self.capture_backend).__name__ != "MssCaptureBackend":
            return None
        try:
            return WindowsCursorOverlay()
        except Exception:
            return None

    def _get_screen_size(self):
        return self.capture_backend.get_screen_size()

    def _fallback_screen_size(self):
        return 1920, 1080

    def _ensure_screen_size(self):
        if self.sw is None or self.sh is None:
            try:
                screen_size = self._get_screen_size()
                if (
                    isinstance(screen_size, (tuple, list))
                    and len(screen_size) == 2
                    and all(isinstance(value, (int, float)) for value in screen_size)
                ):
                    self.sw, self.sh = int(screen_size[0]), int(screen_size[1])
                else:
                    self.sw, self.sh = self._fallback_screen_size()
            except Exception:
                self.sw, self.sh = self._fallback_screen_size()
        return self.sw, self.sh

    def _get_mouse_position(self):
        return self.mouse_provider.get_position()

    def _validate_capture_backend(self):
        try:
            self.capture_backend.validate()
        except Exception as exc:
            backend_name = type(self.capture_backend).__name__
            message = (
                f"No se pudo iniciar la captura de pantalla con {backend_name}. "
                "El entorno actual no parece ser compatible con el backend de captura seleccionado."
            )
            raise RecordingEnvironmentError(message) from exc

    def start(self):
        self._validate_capture_backend()
        self._ensure_screen_size()
        self.session.reset(time.perf_counter())
        self.mouse_provider.start_listener(self._on_click)
        self._start_keyboard_listener()
        if self._audio_recorder is not None:
            self._audio_recorder.start()

        self._temp_writer, self._temp_path = self._create_temp_writer()
        self._start_async_writer()

        self.thread = threading.Thread(target=self._record_loop)
        self.thread.start()

    def stop_capture(self) -> RecordingArtifact:
        self.session.stop(time.perf_counter())
        self.mouse_provider.stop_listener()
        self._stop_keyboard_listener()
        self.thread.join()

        audio_wav = None
        if self._audio_recorder is not None:
            wav_path = self.filename.replace(".mp4", "_audio.wav")
            audio_wav = self._audio_recorder.stop(wav_path)

        screen_width, screen_height = self._ensure_screen_size()
        artifact = RecordingArtifact(
            filename=self.filename,
            settings=self.settings,
            screen_size=(screen_width, screen_height),
            raw_data=tuple(self._injected_raw_data),
            mouse_data=tuple(self.session.mouse_data),
            temp_path=self._temp_path,
            audio_wav=audio_wav,
        )
        self._injected_raw_data = []
        self._temp_path = ""
        return artifact

    def render_recording(self, artifact: RecordingArtifact, callback_progress=None, export_mode="full"):
        self._render_adaptive_video(
            artifact,
            callback_progress=callback_progress,
            export_mode=export_mode,
        )

        if artifact.audio_wav and os.path.exists(artifact.audio_wav):
            from .infrastructure.encoding.h264_encoder import add_audio_to_video
            if export_mode in ("full", "both"):
                add_audio_to_video(artifact.filename, artifact.audio_wav)
            if export_mode in ("tiktok", "both"):
                tiktok_path = artifact.filename.replace(".mp4", "_tiktok.mp4")
                if os.path.exists(tiktok_path):
                    add_audio_to_video(tiktok_path, artifact.audio_wav)
            os.remove(artifact.audio_wav)

    def stop(self, callback_progress=None, export_mode="full"):
        artifact = self.stop_capture()
        self.render_recording(
            artifact,
            callback_progress=callback_progress,
            export_mode=export_mode,
        )

    def _record_loop(self):
        frame_interval = 1.0 / self.settings.fps
        try:
            self.capture_backend.start()
            next_capture_at = time.perf_counter()
            while self.session.is_recording:
                if self.session.is_paused:
                    time.sleep(0.05)
                    next_capture_at = time.perf_counter() + frame_interval
                    continue
                now = time.perf_counter()
                remaining = next_capture_at - now
                if remaining > 0:
                    time.sleep(min(remaining, 0.005))
                    continue

                frame = self.capture_backend.capture_frame()
                if frame is None:
                    next_capture_at = max(next_capture_at + frame_interval, time.perf_counter())
                    continue
                mx, my = self._get_mouse_position()
                if self._cursor_overlay is not None:
                    try:
                        frame = self._cursor_overlay.apply_to_frame(frame, mx, my, self.session.is_clicking)
                    except Exception:
                        self._cursor_overlay = None

                capture_time = time.perf_counter()
                ts = self.session.elapsed(capture_time)

                if self._temp_writer is not None:
                    self._write_temp_frame(frame)
                else:
                    # fallback RAM (tests o si XVID no está disponible)
                    self._injected_raw_data.append(
                        (frame.copy(), mx, my, self.session.is_clicking, ts)
                    )

                self.session.append_sample(
                    FrameSample(
                        frame=frame,  # referencia temporal solo para preview
                        mouse_x=mx,
                        mouse_y=my,
                        is_clicking=self.session.is_clicking,
                        timestamp=ts,
                    )
                )
                next_capture_at += frame_interval
                if capture_time - next_capture_at > frame_interval * 2:
                    next_capture_at = capture_time + frame_interval
        finally:
            self.capture_backend.stop()
            self._stop_async_writer()

    def _render_adaptive_video(self, artifact: RecordingArtifact, callback_progress, export_mode):
        if artifact.raw_data:
            if self.sw is None or self.sh is None:
                first_frame = artifact.raw_data[0][0]
                self.sh, self.sw = first_frame.shape[:2]
            self.renderer.render(
                raw_data=artifact.raw_data,
                settings=artifact.settings,
                screen_size=artifact.screen_size,
                output_filename=artifact.filename,
                callback_progress=callback_progress,
                export_mode=export_mode,
            )
        elif artifact.temp_path and os.path.exists(artifact.temp_path):
            self.renderer.render_from_file(
                temp_path=artifact.temp_path,
                mouse_data=artifact.mouse_data,
                settings=artifact.settings,
                screen_size=artifact.screen_size,
                output_filename=artifact.filename,
                callback_progress=callback_progress,
                export_mode=export_mode,
            )
            os.remove(artifact.temp_path)

    def _create_temp_writer(self):
        screen_width, screen_height = self._ensure_screen_size()
        codec_candidates = [
            ("MJPG", ".avi"),
            ("mp4v", ".mp4"),
            ("XVID", ".avi"),
            ("HFYU", ".avi"),
        ]
        for codec, extension in codec_candidates:
            temp_path = self.filename.replace(".mp4", f"_temp_raw{extension}")
            fourcc = cv2.VideoWriter_fourcc(*codec)  # type: ignore[attr-defined]
            writer = cv2.VideoWriter(temp_path, fourcc, self.settings.fps, (screen_width, screen_height))
            if writer.isOpened():
                return writer, temp_path
            writer.release()
        return None, ""

    def _start_async_writer(self):
        if self._temp_writer is None:
            return
        self._writer_error = None
        self._writer_queue = queue.Queue(maxsize=90)
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()

    def _write_temp_frame(self, frame):
        if self._temp_writer is None:
            return
        if self._writer_queue is None:
            self._temp_writer.write(frame)
            return
        try:
            self._writer_queue.put(frame, timeout=0.003)
        except queue.Full:
            try:
                self._writer_queue.get_nowait()
                self._writer_queue.task_done()
            except queue.Empty:
                pass
            try:
                self._writer_queue.put_nowait(frame)
            except queue.Full:
                pass

    def _writer_loop(self):
        writer_queue = self._writer_queue
        if writer_queue is None:
            return

        while True:
            try:
                frame = writer_queue.get(timeout=0.1)
            except queue.Empty:
                if not self.session.is_recording:
                    break
                continue

            if frame is None:
                writer_queue.task_done()
                break

            try:
                self._temp_writer.write(frame)
            except Exception as exc:
                self._writer_error = exc
                writer_queue.task_done()
                break

            writer_queue.task_done()

    def _stop_async_writer(self):
        if self._writer_queue is not None:
            try:
                self._writer_queue.put(None, timeout=0.2)
            except queue.Full:
                pass
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=2.0)
            self._writer_thread = None
        self._writer_queue = None
        if self._temp_writer is not None:
            self._temp_writer.release()
            self._temp_writer = None

    def _zoomed_crop(self, tiktok: bool = False):
        import numpy as np
        frame = self.session.latest_frame
        if frame is None:
            return None
        sh, sw = frame.shape[:2]
        mx = self.session.latest_mx
        my = self.session.latest_my
        zn = self.settings.zoom
        if tiktok:
            z_h = int(sh / zn)
            z_w = min(int(z_h * 9 / 16), sw)
            z_h = min(z_h, sh)
        else:
            z_w = int(sw / zn)
            z_h = int(sh / zn)
        x1 = int(np.clip(mx - z_w // 2, 0, sw - z_w))
        y1 = int(np.clip(my - z_h // 2, 0, sh - z_h))
        return frame[y1:y1 + z_h, x1:x1 + z_w]

    @property
    def preview_frame(self):
        return self._zoomed_crop(tiktok=False)

    @property
    def preview_frame_tiktok(self):
        return self._zoomed_crop(tiktok=True)

    @property
    def audio_level(self) -> int:
        if self._audio_recorder is None:
            return 0
        return self._audio_recorder.level

    @property
    def is_recording(self):
        return self.session.is_recording

    @is_recording.setter
    def is_recording(self, value):
        self.session.is_recording = value

    @property
    def is_clicking(self):
        return self.session.is_clicking

    @is_clicking.setter
    def is_clicking(self, value):
        self.session.is_clicking = value

    @property
    def start_time(self):
        return self.session.start_time

    @start_time.setter
    def start_time(self, value):
        self.session.start_time = value

    @property
    def raw_data(self):
        return self._injected_raw_data

    @raw_data.setter
    def raw_data(self, value):
        self._injected_raw_data = value

    @property
    def is_paused(self):
        return self.session.is_paused

    def toggle_pause(self):
        if not self.session.is_recording:
            return False
        if self.session.is_paused:
            self.session.resume()
            if self._audio_recorder is not None:
                self._audio_recorder.resume()
        else:
            self.session.pause()
            if self._audio_recorder is not None:
                self._audio_recorder.pause()
        paused = self.session.is_paused
        if callable(self.on_pause_toggled):
            self.on_pause_toggled(paused)
        return paused

    def request_stop(self):
        if self.session.is_recording and callable(self.on_stop_requested):
            self.on_stop_requested()

    def get_elapsed_time(self):
        return self.session.elapsed()

    def _start_keyboard_listener(self):
        try:
            if self._keyboard_module is None:
                from pynput import keyboard as pynput_keyboard

                self._keyboard_module = pynput_keyboard
            self._keyboard_listener = self._keyboard_module.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._keyboard_listener.start()
        except Exception:
            self._keyboard_listener = None
            self._keyboard_module = None

    def _stop_keyboard_listener(self):
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        self._hotkeys_down.clear()

    def _on_key_press(self, key):
        keyboard_module = self._keyboard_module
        if keyboard_module is None:
            return
        if key in self._hotkeys_down:
            return
        self._hotkeys_down.add(key)
        if key == self._resolve_hotkey(self.settings.pause_hotkey, keyboard_module.Key.f7):
            self.toggle_pause()
        elif key == self._resolve_hotkey(self.settings.stop_hotkey, keyboard_module.Key.f10):
            self.request_stop()

    def _on_key_release(self, key):
        self._hotkeys_down.discard(key)

    @staticmethod
    def _resolve_hotkey(hotkey_name: str, fallback):
        key_type = fallback.__class__
        return getattr(key_type, (hotkey_name or "").lower(), fallback)
