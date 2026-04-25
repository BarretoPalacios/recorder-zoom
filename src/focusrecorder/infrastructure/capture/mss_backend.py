import cv2
import numpy as np
import mss

from ...domain.ports.capture_backend import CaptureBackend


class MssCaptureBackend(CaptureBackend):
    def __init__(self):
        self.sct = None
        self.monitor = None
        self._supports_native_cursor = False

    def _create_mss(self):
        try:
            sct = mss.mss(with_cursor=True)
            self._supports_native_cursor = True
            return sct
        except TypeError:
            self._supports_native_cursor = False
            return mss.mss()
        except Exception:
            self._supports_native_cursor = False
            return mss.mss()

    def get_screen_size(self) -> tuple[int, int]:
        with self._create_mss() as sct:
            monitor = sct.monitors[0]
            return monitor["width"], monitor["height"]

    def start(self):
        self.sct = self._create_mss()
        self.monitor = self.sct.monitors[0]

    def validate(self):
        try:
            self.start()
            self.capture_frame()
        finally:
            self.stop()

    def capture_frame(self):
        if self.sct is None or self.monitor is None:
            raise RuntimeError("MssCaptureBackend must be started before capture")

        sct_img = self.sct.grab(self.monitor)
        frame = np.array(sct_img)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    def stop(self):
        if self.sct is not None:
            self.sct.close()
        self.sct = None
        self.monitor = None
