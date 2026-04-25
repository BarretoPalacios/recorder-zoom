import os
from dataclasses import dataclass, replace
from pathlib import Path

from ...config.config import (
    get_app_config,
    save_user_preferences_from_settings,
    with_recording_overrides,
)
from ...config.settings import UISettings, UserPreferences
from ...application.dto import RecordingArtifact, StopRecordingResult
from ...application.use_cases.prepare_recording import PrepareRecordingUseCase
from ...application.use_cases.render_recording import RenderRecordingUseCase
from ...application.use_cases.start_recording import StartRecordingUseCase
from ...application.use_cases.stop_recording import StopRecordingUseCase
from ...infrastructure.system.shell_paths import reveal_file, reveal_folder
from .ui_conversions import (
    recording_suavidad_to_ui,
    recording_zoom_to_ui,
    ui_suavidad_to_recording,
    ui_zoom_to_recording,
)


DEFAULT_START_BUTTON_TEXT = "INICIAR GRABACIÓN"
DEFAULT_START_BUTTON_STYLE = "background: #28a745; color: white; font-weight: bold;"
STOP_BUTTON_TEXT = "DETENER Y PROCESAR"
STOP_BUTTON_STYLE = "background: #dc3545; color: white; font-weight: bold;"


@dataclass(frozen=True)
class StartRecordingViewModel:
    status_text: str
    button_text: str = STOP_BUTTON_TEXT
    button_style: str = STOP_BUTTON_STYLE


@dataclass(frozen=True)
class RenderRecordingViewModel:
    status_text: str


@dataclass(frozen=True)
class FinishedRecordingViewModel:
    status_text: str
    primary_path: str = ""
    full_path: str = ""
    tiktok_path: str = ""
    button_text: str = DEFAULT_START_BUTTON_TEXT
    button_style: str = DEFAULT_START_BUTTON_STYLE


class RecordingPresenter:
    def __init__(
        self,
        app_config=None,
        start_recording_use_case=None,
        stop_recording_use_case=None,
        prepare_recording_use_case=None,
        render_recording_use_case=None,
    ):
        self.app_config = app_config or get_app_config()
        self.start_recording_use_case = start_recording_use_case or StartRecordingUseCase()
        self.stop_recording_use_case = stop_recording_use_case or StopRecordingUseCase()
        self.prepare_recording_use_case = prepare_recording_use_case or PrepareRecordingUseCase()
        self.render_recording_use_case = render_recording_use_case or RenderRecordingUseCase()
        self.recorder = None
        self._prepared_recorder = None
        self._prepared_artifact = None
        self.last_result = StopRecordingResult("", "")

    @property
    def default_recording_settings(self):
        return self.app_config.user_preferences.recording

    def get_output_dir_display(self):
        return str(self.default_recording_settings.output_dir)

    def get_default_ui_state(self):
        recording = self.app_config.user_preferences.recording
        return {
            "zoom": recording_zoom_to_ui(recording.zoom),
            "suavidad": recording_suavidad_to_ui(recording.suavidad),
            "fps": recording.fps,
            "export_mode": self.app_config.user_preferences.ui.export_mode,
            "preview_enabled": self.app_config.user_preferences.ui.preview_enabled,
            "audio": recording.audio,
            "audio_mode": recording.audio_mode,
            "pause_hotkey": recording.pause_hotkey,
            "stop_hotkey": recording.stop_hotkey,
            "quality": recording.quality,
            "render_quality": recording.render_quality,
        }

    def has_active_recording(self):
        return self.recorder is not None and self.recorder.is_recording

    def start_recording(self, *, zoom, suavidad, fps, custom_name="", audio=False, audio_mode="mic", audio_device=None, pause_hotkey="f7", stop_hotkey="f10", quality="high", render_quality="normal"):
        self.save_current_preferences(zoom=zoom, suavidad=suavidad, fps=fps, audio=audio, audio_mode=audio_mode, pause_hotkey=pause_hotkey, stop_hotkey=stop_hotkey, quality=quality, render_quality=render_quality)
        settings = replace(
            self.app_config.user_preferences.recording,
            custom_name=custom_name,
            audio_mode=audio_mode,
            audio_device=audio_device,
            pause_hotkey=pause_hotkey,
            stop_hotkey=stop_hotkey,
            quality=quality,
            render_quality=render_quality,
        )
        result = self.start_recording_use_case.execute(settings)
        self.recorder = result.recorder
        filename = os.path.basename(result.filename)
        return StartRecordingViewModel(status_text=f"🔴 Grabando...\n{filename}")

    def build_rendering_view_model(self, export_mode):
        label = {
            "full": "pantalla completa",
            "tiktok": "TikTok 9:16",
            "both": "ambos formatos",
        }[export_mode]
        return RenderRecordingViewModel(status_text=f"⚙️ Renderizando {label}...")

    def stop_recording(self, export_mode, callback_progress=None):
        if self.recorder is None:
            raise RuntimeError("No active recording to stop")

        result = self.stop_recording_use_case.execute(
            self.recorder,
            callback_progress=callback_progress,
            export_mode=export_mode,
        )
        self.recorder = None
        return result

    def prepare_stop_recording(self) -> RecordingArtifact:
        if self.recorder is None:
            raise RuntimeError("No active recording to stop")
        recorder = self.recorder
        artifact = self.prepare_recording_use_case.execute(recorder)
        self.recorder = None
        self._prepared_recorder = recorder
        self._prepared_artifact = artifact
        return artifact

    def render_prepared_recording(self, export_mode, callback_progress=None):
        if self._prepared_recorder is None or self._prepared_artifact is None:
            raise RuntimeError("No prepared recording to render")
        try:
            return self.render_recording_use_case.execute(
                self._prepared_recorder,
                self._prepared_artifact,
                callback_progress=callback_progress,
                export_mode=export_mode,
            )
        finally:
            self._prepared_recorder = None
            self._prepared_artifact = None

    def build_finished_view_model(self, result: StopRecordingResult):
        self.last_result = result
        lines = ["✅ Guardado:"]
        if result.full_path:
            lines.append(f"📺 {os.path.basename(result.full_path)}")
        if result.tiktok_path:
            lines.append(f"📱 {os.path.basename(result.tiktok_path)}")
        return FinishedRecordingViewModel(
            status_text="\n".join(lines),
            primary_path=result.tiktok_path or result.full_path or "",
            full_path=result.full_path,
            tiktok_path=result.tiktok_path,
        )

    def save_current_preferences(self, *, zoom, suavidad, fps, export_mode=None, audio=None, audio_mode=None, preview_enabled=None, pause_hotkey=None, stop_hotkey=None, quality=None, render_quality=None):
        updated_recording = with_recording_overrides(
            self.app_config.user_preferences.recording,
            zoom=ui_zoom_to_recording(zoom),
            suavidad=ui_suavidad_to_recording(suavidad),
            fps=fps,
            audio=audio,
            audio_mode=audio_mode,
            pause_hotkey=pause_hotkey,
            stop_hotkey=stop_hotkey,
            quality=quality,
            render_quality=render_quality,
        )
        updated_ui = UISettings(
            export_mode=export_mode or self.app_config.user_preferences.ui.export_mode,
            preview_enabled=self.app_config.user_preferences.ui.preview_enabled if preview_enabled is None else preview_enabled,
        )
        self._save_preferences(UserPreferences(recording=updated_recording, ui=updated_ui))

    def update_output_directory(self, output_dir: str | Path):
        updated_recording = replace(
            self.app_config.user_preferences.recording,
            output_dir=Path(output_dir),
        )
        self._save_preferences(
            UserPreferences(
                recording=updated_recording,
                ui=self.app_config.user_preferences.ui,
            )
        )

    def reveal_output_directory(self):
        return reveal_folder(self.app_config.user_preferences.recording.output_dir)

    def reveal_last_export(self):
        target_path = self.get_last_export_path()
        if target_path:
            return reveal_file(target_path)
        return False

    def get_last_export_path(self):
        return self.last_result.tiktok_path or self.last_result.full_path or self.get_latest_saved_video()

    def get_latest_saved_video(self):
        output_dir = Path(self.app_config.user_preferences.recording.output_dir)
        if not output_dir.exists():
            return ""
        candidates = [
            path for path in output_dir.glob("*.mp4")
            if path.is_file() and not path.name.endswith("_temp_raw.mp4")
        ]
        if not candidates:
            return ""
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        return str(latest)

    def _save_preferences(self, preferences: UserPreferences):
        save_user_preferences_from_settings(preferences)
        self.app_config = replace(self.app_config, user_preferences=preferences)
