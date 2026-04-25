import os
import sys

from PyQt6.QtWidgets import QApplication

from .presentation.qt.render_thread import RenderThread
from .presentation.qt.studio_window import FocusApp

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"


def run():
    app = QApplication(sys.argv)
    ex = FocusApp()
    ex.show()
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    run()
