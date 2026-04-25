from PyQt6.QtCore import QThread, pyqtSignal


class RenderThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self, presenter, export_mode):
        super().__init__()
        self.presenter = presenter
        self.export_mode = export_mode

    def run(self):
        result = self.presenter.render_prepared_recording(
            self.export_mode,
            callback_progress=self.progress.emit,
        )
        self.finished.emit(result)
