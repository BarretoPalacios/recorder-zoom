import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt
from recorder import TelemetryRecorder
from editor_ui import FocusEditor # Importamos tu nueva interfaz

class LauncherApp(QWidget):
    def __init__(self):
        super().__init__()
        self.recorder = TelemetryRecorder()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FocusSee Suite")
        self.setFixedWidth(300)
        
        layout = QVBoxLayout()
        
        self.status = QLabel("¿Qué deseas hacer?")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        # Botón para Grabar
        self.btn_record = QPushButton("🔴 INICIAR GRABADOR")
        self.btn_record.clicked.connect(self.toggle_record)
        self.btn_record.setStyleSheet("height: 40px; background: #28a745; color: white;")
        layout.addWidget(self.btn_record)

        # Botón para Editar
        self.btn_edit = QPushButton("🎬 ABRIR EDITOR")
        self.btn_edit.clicked.connect(self.open_editor)
        self.btn_edit.setStyleSheet("height: 40px; background: #007bff; color: white;")
        layout.addWidget(self.btn_edit)

        self.setLayout(layout)

    def toggle_record(self):
        if not self.recorder.is_recording:
            self.recorder.start()
            self.btn_record.setText("⏹️ DETENER GRABACIÓN")
            self.status.setText("Capturando telemetría...")
        else:
            self.recorder.stop()
            self.btn_record.setText("🔴 INICIAR GRABADOR")
            self.status.setText("Grabación guardada.")

    def open_editor(self):
        # Cerramos esta ventana y abrimos el editor
        self.editor_window = FocusEditor()
        self.editor_window.show()
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = LauncherApp()
    launcher.show()
    sys.exit(app.exec())