import os
import platform
import subprocess
from pathlib import Path


def reveal_folder(folder_path: Path | str) -> bool:
    folder_path = Path(folder_path)
    folder_path.mkdir(parents=True, exist_ok=True)
    folder_str = str(folder_path.resolve())
    system = platform.system()

    try:
        if system == "Windows":
            subprocess.Popen(["explorer", folder_str])
        elif system == "Darwin":
            subprocess.Popen(["open", folder_str])
        else:
            subprocess.Popen(["xdg-open", folder_str])
        return True
    except Exception:
        if system == "Windows":
            try:
                os.startfile(folder_str)  # type: ignore[attr-defined]
                return True
            except Exception:
                return False
        return False


def reveal_file(file_path: Path | str) -> bool:
    file_path = Path(file_path)
    if not file_path.exists():
        return False

    system = platform.system()
    file_str = str(file_path.resolve())

    try:
        if system == "Windows":
            subprocess.Popen(["explorer", "/select,", file_str])
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", file_str])
        else:
            return reveal_folder(file_path.parent)
        return True
    except Exception:
        return reveal_folder(file_path.parent)
