import sys
import cv2
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QSlider, QPushButton, QLabel, QCheckBox, QProgressBar)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from composer import VideoComposer

class FocusEditor(QWidget):
    def __init__(self):
        super().__init__()
        try:
            self.composer = VideoComposer("video_raw.mp4", "telemetry.json")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit()

        self.current_time = 0.0
        self.is_playing = False
        self.play_start_time = 0
        
        # Primero inicializamos la UI (esto crea los objetos como time_label)
        self.init_ui()
        
        # Luego el timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_time)

    def init_ui(self):
        self.setWindowTitle("FocusSee Suite - Editor & Export")
        self.setStyleSheet("background-color: #121212; color: #eee;")
        layout = QVBoxLayout()

        # 1. MONITOR DE VIDEO
        self.video_label = QLabel("Preview")
        self.video_label.setFixedSize(854, 480)
        self.video_label.setStyleSheet("background: black; border: 1px solid #333; border-radius: 10px;")
        layout.addWidget(self.video_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 2. LÍNEA DE TIEMPO
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        max_t = self.composer.telemetry["events"][-1]["t"]
        self.timeline.setRange(0, int(max_t * 100))
        self.timeline.sliderMoved.connect(self.seek_video) 
        layout.addWidget(self.timeline)

        # 3. PANEL DE AJUSTES (Zoom y Suavizado)
        settings = QHBoxLayout()
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 40)
        self.zoom_slider.setValue(18)
        self.zoom_slider.valueChanged.connect(self.update_preview)
        
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(1, 50)
        self.smooth_slider.setValue(10)
        self.smooth_slider.valueChanged.connect(self.update_smoothing)
        
        self.zoom_check = QCheckBox("Activar Zoom")
        self.zoom_check.setChecked(True)
        self.zoom_check.stateChanged.connect(self.update_preview)

        settings.addWidget(QLabel("Zoom:"))
        settings.addWidget(self.zoom_slider)
        settings.addWidget(QLabel("Suavizado:"))
        settings.addWidget(self.smooth_slider)
        settings.addWidget(self.zoom_check)
        layout.addLayout(settings)

        # 4. BOTONES Y ETIQUETA DE TIEMPO
        actions = QHBoxLayout()
        self.play_btn = QPushButton("▶ PLAY")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setStyleSheet("background: #007bff; height: 40px; border-radius: 5px;")
        
        self.export_btn = QPushButton("💾 EXPORTAR MP4")
        self.export_btn.clicked.connect(self.start_export)
        self.export_btn.setStyleSheet("background: #28a745; height: 40px; font-weight: bold; border-radius: 5px;")
        
        # IMPORTANTE: Creamos time_label ANTES de llamar a update_preview
        self.time_label = QLabel(f"0.00s / {max_t:.2f}s")
        self.time_label.setStyleSheet("font-family: monospace; font-size: 14px;")
        
        actions.addWidget(self.play_btn)
        actions.addWidget(self.export_btn)
        actions.addWidget(self.time_label)
        layout.addLayout(actions)

        # BARRA DE PROGRESO (Oculta por defecto)
        self.pbar = QProgressBar()
        self.pbar.hide()
        layout.addWidget(self.pbar)

        self.setLayout(layout)
        
        # Ahora sí, actualizamos el primer frame con todos los objetos creados
        self.update_preview()

    def update_smoothing(self):
        self.composer.smoothing_factor = self.smooth_slider.value() / 100.0

    def start_export(self):
        self.export_btn.setEnabled(False)
        self.pbar.show()
        zoom = self.zoom_slider.value() / 10.0
        is_zoom = self.zoom_check.isChecked()
        smooth = self.smooth_slider.value() / 100.0
        
        self.composer.export_video("resultado_final.mp4", zoom, is_zoom, smooth, self.pbar.setValue)
        
        self.pbar.hide()
        self.export_btn.setEnabled(True)
        self.pbar.setValue(0)

    def toggle_play(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.play_start_time = time.perf_counter() - self.current_time
            self.timer.start(33)
            self.play_btn.setText("⏸ PAUSE")
        else:
            self.timer.stop()
            self.play_btn.setText("▶ PLAY")

    def advance_time(self):
        self.current_time = time.perf_counter() - self.play_start_time
        max_t = self.composer.telemetry["events"][-1]["t"]
        if self.current_time >= max_t:
            self.current_time = 0
            self.toggle_play()
            return
        
        self.timeline.blockSignals(True)
        self.timeline.setValue(int(self.current_time * 100))
        self.timeline.blockSignals(False)
        self.update_preview()

    def seek_video(self, value):
        self.current_time = value / 100.0
        if self.is_playing:
            self.play_start_time = time.perf_counter() - self.current_time
        self.update_preview()

    def update_preview(self):
        zoom = self.zoom_slider.value() / 10.0
        is_enabled = self.zoom_check.isChecked()
        
        frame = self.composer.render_frame(self.current_time, zoom, is_enabled, preview_size=(854, 480))
        
        if frame is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            q_img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            
            pixmap = QPixmap.fromImage(q_img)
            self.video_label.setPixmap(pixmap)
            
            # Actualizamos la etiqueta de tiempo (ahora ya existe)
            max_t = self.composer.telemetry["events"][-1]["t"]
            self.time_label.setText(f"{self.current_time:.2f}s / {max_t:.2f}s")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = FocusEditor()
    editor.show()
    sys.exit(app.exec())