"""User preferences persistence using JSON files."""

import json
from pathlib import Path
from typing import Any

from .constants import (
    CONFIG_FILENAME,
    DEFAULT_ZOOM,
    DEFAULT_SUAVIDAD,
    DEFAULT_FPS,
    DEFAULT_EXPORT_MODE,
    DEFAULT_OUTPUT_FOLDER_NAME,
    DEFAULT_AUDIO,
)
from ..infrastructure.system.platform_paths import get_config_directory


def get_config_file_path() -> Path:
    """Get the full path to the configuration file."""
    return get_config_directory() / CONFIG_FILENAME


def get_example_config_file_path() -> Path:
    """Get the full path to the example configuration file."""
    return get_config_directory() / f"{CONFIG_FILENAME}.example"


def _create_example_config_file() -> None:
    """Create an example configuration file for user reference."""
    example_path = get_example_config_file_path()
    
    if example_path.exists():
        return  # Don't overwrite existing example
    
    example_data = _get_default_preferences()
    
    try:
        with open(example_path, "w", encoding="utf-8") as f:
            json.dump(example_data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # Silently fail if we can't write


def load_user_preferences() -> dict[str, Any]:
    """
    Load user preferences from JSON file.
    Returns default values if file doesn't exist or is invalid.
    Creates an example config file on first run.
    """
    config_path = get_config_file_path()
    
    # Create example file for reference
    _create_example_config_file()
    
    if not config_path.exists():
        # Create initial config file with defaults
        defaults = _get_default_preferences()
        save_user_preferences(defaults)
        return defaults
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate and merge with defaults
        return _merge_with_defaults(data)
    except (json.JSONDecodeError, OSError):
        # If file is corrupted, return defaults
        return _get_default_preferences()


def save_user_preferences(preferences: dict[str, Any]) -> None:
    """Save user preferences to JSON file."""
    config_path = get_config_file_path()
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(preferences, f, indent=2, ensure_ascii=False)
    except OSError:
        # Silently fail if we can't write
        pass


def _get_default_preferences() -> dict[str, Any]:
    """Get default preference values."""
    return {
        "zoom": DEFAULT_ZOOM,
        "suavidad": DEFAULT_SUAVIDAD,
        "fps": DEFAULT_FPS,
        "export_mode": DEFAULT_EXPORT_MODE,
        "output_dir": str(Path.home() / "Desktop" / DEFAULT_OUTPUT_FOLDER_NAME),
        "audio": DEFAULT_AUDIO,
        "audio_mode": "mic",
        "preview_enabled": True,
        "pause_hotkey": "f7",
        "stop_hotkey": "f10",
        "quality": "high",
        "render_quality": "normal",
    }


def _merge_with_defaults(user_data: dict[str, Any]) -> dict[str, Any]:
    """Merge user data with defaults, ensuring all required keys exist."""
    defaults = _get_default_preferences()
    
    # Start with defaults
    merged = defaults.copy()
    
    # Override with valid user values
    if isinstance(user_data.get("zoom"), (int, float)):
        merged["zoom"] = float(user_data["zoom"])
    
    if isinstance(user_data.get("suavidad"), (int, float)):
        merged["suavidad"] = float(user_data["suavidad"])
    
    if isinstance(user_data.get("fps"), int):
        merged["fps"] = user_data["fps"]
    
    if isinstance(user_data.get("export_mode"), str):
        if user_data["export_mode"] in ("full", "tiktok", "both"):
            merged["export_mode"] = user_data["export_mode"]
    
    if isinstance(user_data.get("output_dir"), str):
        # Expand ~ to user home directory
        output_path = Path(user_data["output_dir"]).expanduser()
        merged["output_dir"] = str(output_path)

    if isinstance(user_data.get("audio"), bool):
        merged["audio"] = user_data["audio"]

    if isinstance(user_data.get("audio_mode"), str):
        if user_data["audio_mode"] in ("mic", "system", "both"):
            merged["audio_mode"] = user_data["audio_mode"]

    if isinstance(user_data.get("preview_enabled"), bool):
        merged["preview_enabled"] = user_data["preview_enabled"]

    if isinstance(user_data.get("pause_hotkey"), str):
        merged["pause_hotkey"] = user_data["pause_hotkey"].lower()

    if isinstance(user_data.get("stop_hotkey"), str):
        merged["stop_hotkey"] = user_data["stop_hotkey"].lower()

    if isinstance(user_data.get("quality"), str):
        if user_data["quality"] in ("low", "medium", "high", "very_high"):
            merged["quality"] = user_data["quality"]

    if isinstance(user_data.get("render_quality"), str):
        if user_data["render_quality"] in ("fast", "normal", "high"):
            merged["render_quality"] = user_data["render_quality"]

    return merged
