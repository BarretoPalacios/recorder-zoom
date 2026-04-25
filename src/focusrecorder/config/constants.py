"""Application constants for default configuration values."""

# Recording defaults
DEFAULT_ZOOM: float = 1.0
DEFAULT_SUAVIDAD: float = 0.05
DEFAULT_FPS: int = 30

# UI defaults
DEFAULT_EXPORT_MODE: str = "full"  # "full", "tiktok", "both"
DEFAULT_AUDIO: bool = False

# UI range constraints
MIN_ZOOM: float = 1.0
MAX_ZOOM: float = 4.0
MIN_SUAVIDAD: float = 0.01
MAX_SUAVIDAD: float = 0.20
MIN_FPS: int = 24
MAX_FPS: int = 60

# UI control ranges (for SpinBox and Slider)
# Zoom spinbox trabaja en décimas (x10)
UI_MIN_ZOOM: int = int(MIN_ZOOM * 10)  # 10
UI_MAX_ZOOM: int = int(MAX_ZOOM * 10)  # 40
UI_DEFAULT_ZOOM: int = int(DEFAULT_ZOOM * 10)  # 18

# Suavidad slider trabaja en centésimas (x100)
UI_MIN_SUAVIDAD: int = int(MIN_SUAVIDAD * 100)  # 1
UI_MAX_SUAVIDAD: int = int(MAX_SUAVIDAD * 100)  # 20
UI_DEFAULT_SUAVIDAD: int = int(DEFAULT_SUAVIDAD * 100)  # 5

# FPS no necesita conversión
UI_MIN_FPS: int = MIN_FPS  # 24
UI_MAX_FPS: int = MAX_FPS  # 60
UI_DEFAULT_FPS: int = DEFAULT_FPS  # 30

# File settings
CONFIG_FILENAME: str = "focus_recorder_preferences.json"
DEFAULT_OUTPUT_FOLDER_NAME: str = "videos"
VIDEO_FILE_PREFIX: str = "video_"
VIDEO_FILE_EXTENSION: str = ".mp4"
TIKTOK_SUFFIX: str = "_tiktok"
