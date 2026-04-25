import cv2
import numpy as np
import subprocess

import imageio_ffmpeg

from ..encoding.h264_encoder import build_h264_ffmpeg_args, can_encode_with_ffmpeg, get_candidate_video_encoders, reencode_to_h264, summarize_ffmpeg_error


class FFmpegWriterError(RuntimeError):
    pass


class FFmpegVideoWriter:
    def __init__(self, filename: str, fps: int, frame_size: tuple[int, int], encoder: str, quality: str):
        self.filename = filename
        self.fps = fps
        self.width, self.height = frame_size
        self.encoder = encoder
        self.quality = quality
        self.process = None
        self._stderr = ""
        self._start()

    def _start(self):
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",
            *build_h264_ffmpeg_args(self.encoder, self.quality),
            "-an",
            self.filename,
        ]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._ensure_alive()

    def _read_stderr(self) -> str:
        if self.process is None or self.process.stderr is None:
            return ""
        try:
            data = self.process.stderr.read()
        except Exception:
            return self._stderr
        if not data:
            return self._stderr
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = data
        self._stderr = text.strip() or self._stderr
        return self._stderr

    def _ensure_alive(self):
        if self.process is None:
            raise FFmpegWriterError("FFmpeg no pudo iniciar")
        return_code = self.process.poll()
        if return_code is not None:
            message = summarize_ffmpeg_error(self._read_stderr()) or f"FFmpeg finalizo antes de tiempo con codigo {return_code}"
            raise FFmpegWriterError(message)

    def write(self, frame):
        if self.process is None or self.process.stdin is None:
            raise FFmpegWriterError("FFmpeg writer is not available")
        self._ensure_alive()
        try:
            self.process.stdin.write(frame.tobytes())
        except BrokenPipeError as exc:
            message = summarize_ffmpeg_error(self._read_stderr()) or "FFmpeg cerro la tuberia de entrada"
            raise FFmpegWriterError(message) from exc

    def release(self):
        if self.process is None:
            return
        return_code = 0
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        return_code = self.process.wait()
        if return_code != 0:
            message = summarize_ffmpeg_error(self._read_stderr()) or f"FFmpeg finalizo con codigo {return_code}"
            self.process = None
            raise FFmpegWriterError(message)
        self.process = None


class AdaptiveVideoRenderer:
    @staticmethod
    def _can_encode_with_ffmpeg(encoder, width, height, fps, quality):
        try:
            return can_encode_with_ffmpeg(encoder, width, height, fps, quality)
        except TypeError:
            return can_encode_with_ffmpeg(encoder, width, height, fps)

    @staticmethod
    def _build_ffmpeg_writer(filename, fps, frame_size, encoder, quality):
        try:
            return FFmpegVideoWriter(filename, fps, frame_size, encoder, quality)
        except TypeError:
            return FFmpegVideoWriter(filename, fps, frame_size, encoder)

    @classmethod
    def _create_compatible_writer(cls, filename, fps, frame_size, quality):
        try:
            return cls._create_writer(filename, fps, frame_size, quality)
        except TypeError:
            return cls._create_writer(filename, fps, frame_size)

    @staticmethod
    def _reencode_compatible(path, quality):
        try:
            reencode_to_h264(path, quality)
        except TypeError:
            reencode_to_h264(path)

    @staticmethod
    def _interpolate_mouse(samples, data_ptr, current_time):
        sample = samples[data_ptr]
        if len(sample) >= 5:
            _frame, mx, my, clicking, ts = sample
        else:
            mx, my, clicking, ts = sample
        if data_ptr >= len(samples) - 1:
            return float(mx), float(my), clicking
        next_sample = samples[data_ptr + 1]
        if len(next_sample) >= 5:
            _next_frame, next_mx, next_my, _next_clicking, next_ts = next_sample
        else:
            next_mx, next_my, _next_clicking, next_ts = next_sample
        span = max(next_ts - ts, 0.0)
        if span <= 1e-6:
            return float(mx), float(my), clicking
        blend = float(np.clip((current_time - ts) / span, 0.0, 1.0))
        ix = float(mx) + (float(next_mx) - float(mx)) * blend
        iy = float(my) + (float(next_my) - float(my)) * blend
        return ix, iy, clicking

    @staticmethod
    def _smooth_follow(current, target, frame_span, smooth, dt):
        delta = float(target - current)
        deadzone = max(frame_span * 0.004, 4.0)
        if abs(delta) <= deadzone:
            return current + delta * 0.08

        effective = delta - np.sign(delta) * deadzone
        responsiveness = float(np.interp(smooth, [0.01, 0.20], [5.0, 13.0]))
        alpha = 1.0 - float(np.exp(-responsiveness * max(dt, 1.0 / 240.0)))
        distance_boost = float(np.clip(abs(effective) / max(frame_span * 0.18, 1.0), 0.0, 1.0))
        alpha = float(np.clip(alpha * (0.75 + 0.85 * distance_boost), 0.06, 0.42))
        max_step = max(frame_span * 0.030, 12.0)
        if distance_boost > 0.65:
            max_step = max(frame_span * 0.055, 22.0)
        step = float(np.clip(effective * alpha, -max_step, max_step))
        return current + step

    @staticmethod
    def _resize_interpolation(quality: str):
        if quality == "high":
            return cv2.INTER_LANCZOS4
        if quality == "normal":
            return cv2.INTER_LINEAR
        return cv2.INTER_AREA

    @staticmethod
    def _enhance_frame(frame, quality: str):
        if quality != "high":
            return frame
        sigma = 0.8
        weight = 1.18
        blurred = cv2.GaussianBlur(frame, (0, 0), sigma)
        return cv2.addWeighted(frame, weight, blurred, -(weight - 1.0), 0)

    @staticmethod
    def _create_writer(filename, fps, frame_size, quality="balanced"):
        width, height = frame_size
        for encoder in get_candidate_video_encoders():
            try:
                if not AdaptiveVideoRenderer._can_encode_with_ffmpeg(encoder, width, height, fps, quality):
                    continue
                return AdaptiveVideoRenderer._build_ffmpeg_writer(filename, fps, frame_size, encoder, quality)
            except Exception:
                continue
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
        return cv2.VideoWriter(filename, fourcc, fps, frame_size)

    def render(
        self,
        *,
        raw_data,
        settings,
        screen_size,
        output_filename,
        callback_progress=None,
        export_mode="full",
    ):
        if not raw_data:
            return

        sw, sh = screen_size
        total_duration = raw_data[-1][4]
        target_fps = int(settings.fps)
        total_frames = max(int(total_duration * target_fps), 1)

        do_full = export_mode in ("full", "both")
        do_tiktok = export_mode in ("tiktok", "both")

        out_full = None
        if do_full:
            out_full = self._create_compatible_writer(output_filename, target_fps, (sw, sh), settings.quality)

        out_tiktok = None
        tiktok_w = tiktok_h = 0
        tiktok_path = ""
        if do_tiktok:
            tiktok_h = sh
            tiktok_w = int(sh * 9 / 16)
            if tiktok_w % 2 != 0:  # pragma: no cover
                tiktok_w += 1
            tiktok_path = output_filename.replace(".mp4", "_tiktok.mp4")
            out_tiktok = self._create_compatible_writer(tiktok_path, target_fps, (tiktok_w, tiktok_h), settings.quality)

        cam_x = float(sw // 2)
        cam_y = float(sh // 2)
        tiktok_cam_x = float(sw // 2)
        tiktok_cam_y = float(sh // 2)
        tiktok_smooth = min(settings.suavidad * 1.5, 1.0)
        data_ptr = 0
        render_weight = 0.8

        for f_idx in range(total_frames):
            current_time = f_idx / target_fps
            dt = 1.0 / max(target_fps, 1)

            while data_ptr < len(raw_data) - 1 and raw_data[data_ptr + 1][4] < current_time:
                data_ptr += 1

            # El mouse solo guia el encuadre del seguimiento.
            # El video sale tal como lo entrega el backend de captura.
            frame, _mx, _my, clicking, _ = raw_data[data_ptr]
            mx, my, clicking = self._interpolate_mouse(raw_data, data_ptr, current_time)
            zn = settings.zoom

            if do_full:
                cam_x = self._smooth_follow(cam_x, mx, sw, settings.suavidad, dt)
                cam_y = self._smooth_follow(cam_y, my, sh, settings.suavidad, dt)

                z_w = int(sw / zn)
                z_h = int(sh / zn)
                x1 = int(np.clip(cam_x - z_w // 2, 0, sw - z_w))
                y1 = int(np.clip(cam_y - z_h // 2, 0, sh - z_h))

                cropped = frame[y1:y1 + z_h, x1:x1 + z_w]

                if cropped.size > 0:  # pragma: no cover
                    final = cv2.resize(
                        cropped,
                        (sw, sh),
                        interpolation=self._resize_interpolation(settings.render_quality),
                    )
                    final = self._enhance_frame(final, settings.render_quality)

                    out_full.write(final)  # type: ignore[union-attr]

            if do_tiktok:
                tiktok_cam_x = self._smooth_follow(tiktok_cam_x, mx, sw, tiktok_smooth, dt)
                tiktok_cam_y = self._smooth_follow(tiktok_cam_y, my, sh, tiktok_smooth, dt)

                z_h_tt = int(sh / zn)
                z_w_tt = min(int(z_h_tt * 9 / 16), sw)
                z_h_tt = min(z_h_tt, sh)

                x1_tt = int(np.clip(tiktok_cam_x - z_w_tt // 2, 0, sw - z_w_tt))
                y1_tt = int(np.clip(tiktok_cam_y - z_h_tt // 2, 0, sh - z_h_tt))

                cropped_tt = frame[y1_tt:y1_tt + z_h_tt, x1_tt:x1_tt + z_w_tt]

                if cropped_tt.size > 0 and tiktok_w > 0 and tiktok_h > 0:  # pragma: no cover
                    final_tt = cv2.resize(
                        cropped_tt,
                        (tiktok_w, tiktok_h),
                        interpolation=self._resize_interpolation(settings.render_quality),
                    )
                    final_tt = self._enhance_frame(final_tt, settings.render_quality)
                    out_tiktok.write(final_tt)  # type: ignore[union-attr]

            if callback_progress and f_idx % 10 == 0:
                pct = int((f_idx / total_frames) * 100 * render_weight)
                callback_progress(pct)

        if out_full:
            out_full.release()
        if out_tiktok:
            out_tiktok.release()

        files_to_encode = []
        if do_full and not isinstance(out_full, FFmpegVideoWriter):
            files_to_encode.append(output_filename)
        if do_tiktok and not isinstance(out_tiktok, FFmpegVideoWriter):
            files_to_encode.append(tiktok_path)

        if files_to_encode:
            for i, path in enumerate(files_to_encode):
                self._reencode_compatible(path, settings.quality)
                if callback_progress:
                    base = int(100 * render_weight)
                    pct = base + int((i + 1) / len(files_to_encode) * (100 - base))
                    callback_progress(pct)
        elif callback_progress:
            callback_progress(int(100 * render_weight))

        if callback_progress:
            callback_progress(100)

    def render_from_file(
        self,
        *,
        temp_path,
        mouse_data,
        settings,
        screen_size,
        output_filename,
        callback_progress=None,
        export_mode="full",
    ):
        cap = cv2.VideoCapture(temp_path)
        total_frames_recorded = len(mouse_data)

        if not cap.isOpened() or total_frames_recorded == 0:
            cap.release()
            return

        total_duration = mouse_data[-1][3]
        target_fps = int(settings.fps)
        total_target_frames = max(int(total_duration * target_fps), 1)

        sw, sh = screen_size
        render_weight = 0.8

        do_full = export_mode in ("full", "both")
        do_tiktok = export_mode in ("tiktok", "both")

        out_full = None
        if do_full:
            out_full = self._create_compatible_writer(output_filename, target_fps, (sw, sh), settings.quality)

        out_tiktok = None
        tiktok_w = tiktok_h = 0
        tiktok_path = ""
        if do_tiktok:
            tiktok_h = sh
            tiktok_w = int(sh * 9 / 16)
            if tiktok_w % 2 != 0:  # pragma: no cover
                tiktok_w += 1
            tiktok_path = output_filename.replace(".mp4", "_tiktok.mp4")
            out_tiktok = self._create_compatible_writer(tiktok_path, target_fps, (tiktok_w, tiktok_h), settings.quality)

        cam_x = float(sw // 2)
        cam_y = float(sh // 2)
        tiktok_cam_x = float(sw // 2)
        tiktok_cam_y = float(sh // 2)
        tiktok_smooth = min(settings.suavidad * 1.5, 1.0)
        zn = settings.zoom

        data_ptr = 0
        ret, current_frame = cap.read()
        if not ret:
            cap.release()
            return

        for f_idx in range(total_target_frames):
            current_time = f_idx / target_fps
            dt = 1.0 / max(target_fps, 1)

            while data_ptr < total_frames_recorded - 1 and mouse_data[data_ptr + 1][3] < current_time:
                data_ptr += 1
                ret, next_frame = cap.read()
                if ret:
                    current_frame = next_frame

            # El mouse solo guia el encuadre del seguimiento.
            # El video sale tal como lo entrega el backend de captura.
            mx, my, clicking = self._interpolate_mouse(mouse_data, data_ptr, current_time)
            frame = current_frame

            if do_full and out_full:
                cam_x = self._smooth_follow(cam_x, mx, sw, settings.suavidad, dt)
                cam_y = self._smooth_follow(cam_y, my, sh, settings.suavidad, dt)

                z_w = int(sw / zn)
                z_h = int(sh / zn)
                x1 = int(np.clip(cam_x - z_w // 2, 0, sw - z_w))
                y1 = int(np.clip(cam_y - z_h // 2, 0, sh - z_h))

                cropped = frame[y1:y1 + z_h, x1:x1 + z_w]
                if cropped.size > 0:  # pragma: no cover
                    final = cv2.resize(
                        cropped,
                        (sw, sh),
                        interpolation=self._resize_interpolation(settings.render_quality),
                    )
                    final = self._enhance_frame(final, settings.render_quality)
                    out_full.write(final)

            if do_tiktok and out_tiktok:
                tiktok_cam_x = self._smooth_follow(tiktok_cam_x, mx, sw, tiktok_smooth, dt)
                tiktok_cam_y = self._smooth_follow(tiktok_cam_y, my, sh, tiktok_smooth, dt)

                z_h_tt = int(sh / zn)
                z_w_tt = min(int(z_h_tt * 9 / 16), sw)
                z_h_tt = min(z_h_tt, sh)

                x1_tt = int(np.clip(tiktok_cam_x - z_w_tt // 2, 0, sw - z_w_tt))
                y1_tt = int(np.clip(tiktok_cam_y - z_h_tt // 2, 0, sh - z_h_tt))

                cropped_tt = frame[y1_tt:y1_tt + z_h_tt, x1_tt:x1_tt + z_w_tt]
                if cropped_tt.size > 0 and tiktok_w > 0 and tiktok_h > 0:  # pragma: no cover
                    final_tt = cv2.resize(
                        cropped_tt,
                        (tiktok_w, tiktok_h),
                        interpolation=self._resize_interpolation(settings.render_quality),
                    )
                    final_tt = self._enhance_frame(final_tt, settings.render_quality)
                    out_tiktok.write(final_tt)

            if callback_progress and f_idx % 10 == 0:
                callback_progress(int((f_idx / total_target_frames) * 100 * render_weight))

        cap.release()

        files_to_encode = []
        if out_full:
            full_needs_reencode = not isinstance(out_full, FFmpegVideoWriter)
            out_full.release()
            if full_needs_reencode:
                files_to_encode.append(output_filename)
        if out_tiktok:
            tiktok_needs_reencode = not isinstance(out_tiktok, FFmpegVideoWriter)
            out_tiktok.release()
            if tiktok_needs_reencode:
                files_to_encode.append(tiktok_path)

        if files_to_encode:
            for i, path in enumerate(files_to_encode):
                self._reencode_compatible(path, settings.quality)
                if callback_progress:
                    base = int(100 * render_weight)
                    callback_progress(base + int((i + 1) / len(files_to_encode) * (100 - base)))
        elif callback_progress:
            callback_progress(int(100 * render_weight))

        if callback_progress:
            callback_progress(100)
