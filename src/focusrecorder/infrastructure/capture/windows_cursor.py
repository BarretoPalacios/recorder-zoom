import cv2
import numpy as np


class WindowsCursorOverlay:
    """Overlay simple basado en coordenadas de mouse, estable y ligero."""

    def __init__(self):
        self._smooth_x = None
        self._smooth_y = None

    def _smooth_position(self, x: int, y: int) -> tuple[int, int]:
        tx = float(x)
        ty = float(y)
        if self._smooth_x is None or self._smooth_y is None:
            self._smooth_x = tx
            self._smooth_y = ty
            return x, y

        dx = tx - self._smooth_x
        dy = ty - self._smooth_y
        distance = float((dx * dx + dy * dy) ** 0.5)

        if distance > 220:
            alpha = 0.34
        elif distance > 110:
            alpha = 0.20
        elif distance > 36:
            alpha = 0.11
        else:
            alpha = 0.06

        self._smooth_x += dx * alpha
        self._smooth_y += dy * alpha
        return int(round(self._smooth_x)), int(round(self._smooth_y))

    @staticmethod
    def _blend_local_glow(
        frame: np.ndarray,
        x: int,
        y: int,
        radius: int,
        color: tuple[int, int, int],
        alpha: float,
    ) -> None:
        h, w = frame.shape[:2]
        pad = radius + 3
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + pad + 1)
        y2 = min(h, y + pad + 1)
        if x1 >= x2 or y1 >= y2:
            return

        roi = frame[y1:y2, x1:x2]
        overlay = roi.copy()
        cv2.circle(overlay, (x - x1, y - y1), radius, color, thickness=-1, lineType=cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0.0, dst=roi)

    def apply_to_frame(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        clicking: bool = False,
    ) -> np.ndarray:
        h, w = frame.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return frame
        x, y = self._smooth_position(x, y)

        if clicking:
            glow_color = (84, 215, 255)
            ring_color = (110, 230, 255)
            core_color = (40, 170, 255)
            glow_alpha = 0.20
            radius = 17
            inner_radius = 5
        else:
            glow_color = (82, 170, 255)
            ring_color = (240, 247, 255)
            core_color = (255, 255, 255)
            glow_alpha = 0.13
            radius = 15
            inner_radius = 4

        self._blend_local_glow(frame, x, y, radius, glow_color, glow_alpha)
        cv2.circle(frame, (x, y), radius - 4, ring_color, thickness=3, lineType=cv2.LINE_AA)
        cv2.circle(frame, (x, y), inner_radius, core_color, thickness=-1, lineType=cv2.LINE_AA)
        return frame
