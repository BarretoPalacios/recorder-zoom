import os
import subprocess
from functools import lru_cache

import imageio_ffmpeg


DEFAULT_CRF = "18"
DEFAULT_CQ = "19"
PREFERRED_ENCODERS = ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")
QUALITY_PRESETS = {
    "low": {"crf": "25", "cq": "28", "x264_preset": "veryfast", "nvenc_preset": "fast"},
    "medium": {"crf": "21", "cq": "23", "x264_preset": "faster", "nvenc_preset": "fast"},
    "high": {"crf": "18", "cq": "19", "x264_preset": "veryfast", "nvenc_preset": "fast"},
    "very_high": {"crf": "15", "cq": "16", "x264_preset": "faster", "nvenc_preset": "medium"},
}


@lru_cache(maxsize=1)
def _available_encoders() -> set[str]:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-encoders"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return set(result.stdout.split())


@lru_cache(maxsize=1)
def _ffmpeg_version() -> tuple[int, ...]:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_exe, "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    for token in first_line.split():
        parts = token.split(".")
        if parts and parts[0].isdigit():
            parsed = []
            for part in parts:
                digits = "".join(char for char in part if char.isdigit())
                if not digits:
                    break
                parsed.append(int(digits))
            if parsed:
                return tuple(parsed)
    return (0,)


def get_preferred_video_encoder() -> str:
    return get_candidate_video_encoders()[0]


def get_candidate_video_encoders() -> list[str]:
    try:
        encoders = _available_encoders()
    except Exception:
        return ["libx264"]

    available = [encoder for encoder in PREFERRED_ENCODERS if encoder in encoders]
    if "libx264" not in available:
        available.append("libx264")
    return available or ["libx264"]


def summarize_ffmpeg_error(message: str) -> str:
    if not message:
        return "FFmpeg no pudo completar el render."
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    relevant = []
    for line in lines:
        lower = line.lower()
        if lower.startswith("ffmpeg version"):
            continue
        if lower.startswith("built with"):
            continue
        if lower.startswith("configuration:"):
            continue
        if lower.startswith("libav"):
            continue
        if lower.startswith("input #"):
            continue
        if lower.startswith("duration:"):
            continue
        if lower.startswith("stream #"):
            continue
        if lower.startswith("stream mapping"):
            continue
        relevant.append(line)
    if not relevant:
        relevant = lines[-3:]
    return "\n".join(relevant[-3:])


@lru_cache(maxsize=16)
def can_encode_with_ffmpeg(encoder: str, width: int, height: int, fps: int, quality: str = "high") -> bool:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r={fps}",
        "-frames:v", "1",
        *build_h264_ffmpeg_args(encoder, quality),
        "-f", "null",
        "-",
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    return result.returncode == 0


def build_h264_ffmpeg_args(encoder: str, quality: str = "high") -> list[str]:
    preset_values = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])
    if encoder == "h264_nvenc":
        ffmpeg_version = _ffmpeg_version()
        preset = "p4" if ffmpeg_version >= (5, 0) else preset_values["nvenc_preset"]
        return ["-c:v", encoder, "-preset", preset, "-cq", preset_values["cq"], "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "medium", "-global_quality", preset_values["cq"], "-look_ahead", "0", "-pix_fmt", "nv12", "-movflags", "+faststart"]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "quality", "-rc", "cqp", "-qp_i", preset_values["cq"], "-qp_p", preset_values["cq"], "-pix_fmt", "nv12", "-movflags", "+faststart"]
    return ["-c:v", "libx264", "-preset", preset_values["x264_preset"], "-crf", preset_values["crf"], "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def reencode_to_h264(input_path: str, quality: str = "high") -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    last_error = ""

    for encoder in get_candidate_video_encoders():
        tmp_path = input_path.replace(".mp4", f"_{encoder}.mp4")
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i",
            input_path,
            "-an",
            *build_h264_ffmpeg_args(encoder, quality),
            tmp_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 and os.path.exists(tmp_path):
            os.remove(input_path)
            os.rename(tmp_path, input_path)
            return
        last_error = result.stderr or last_error
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if os.path.getsize(input_path) > 0:
        return
    raise RuntimeError(summarize_ffmpeg_error(last_error))


def add_audio_to_video(video_path: str, audio_path: str) -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    tmp_path = video_path.replace(".mp4", "_mixed.mp4")

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        tmp_path,
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(tmp_path):  # pragma: no cover
        os.remove(video_path)
        os.rename(tmp_path, video_path)
