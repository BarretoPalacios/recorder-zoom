import sys
import cv2
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QSlider, QPushButton, QLabel, QFrame, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from composer import VideoComposer

class VisualTimeline(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.editor = parent
        self.setMinimumHeight(60)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        max_t = self.editor.max_duration

        painter.fillRect(0, 0, w, h, QColor(30, 30, 30))

        # Dibujar segmentos guardados
        for seg in self.editor.composer.zoom_segments:
            x_start = int((seg["start"] / max_t) * w)
            x_end = int((seg["end"] / max_t) * w)
            rect_w = x_end - x_start
            
            color = QColor(0, 120, 215, 180) if self.editor.selected_id != seg["id"] else QColor(255, 165, 0, 200)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(x_start, 5, rect_w, h - 10)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(x_start + 5, h // 2 + 5, f"Zoom {seg['zoom']}x")

        # Playhead (aguja de tiempo)
        playhead_x = int((self.editor.current_time / max_t) * w)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.drawLine(playhead_x, 0, playhead_x, h)

    def mousePressEvent(self, event):
        w = self.width()
        click_t = (event.position().x() / w) * self.editor.max_duration
        found = False
        for seg in self.editor.composer.zoom_segments:
            if seg["start"] <= click_t <= seg["end"]:
                self.editor.select_segment(seg)
                found = True
                break
        if not found:
            self.editor.selected_id = None
            self.editor.edit_frame.setEnabled(False)
        self.update()

class FocusEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.composer = VideoComposer("video_raw.mp4", "telemetry.json")
        self.current_time = 0.0
        self.max_duration = self.composer.telemetry["events"][-1]["t"]
        self.selected_id = None
        self.is_playing = False
        
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_time)

    def init_ui(self):
        self.setWindowTitle("FocusSee Suite - Editor Visual")
        self.setStyleSheet("background-color: #121212; color: #eee; font-family: sans-serif;")
        layout = QVBoxLayout()

        # 1. MONITOR
        self.video_label = QLabel()
        self.video_label.setFixedSize(854, 480)
        self.video_label.setStyleSheet("background: black; border: 1px solid #333;")
        layout.addWidget(self.video_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 2. TIMELINE VISUAL
        self.timeline_visual = VisualTimeline(self)
        layout.addWidget(self.timeline_visual)

        # 3. SLIDER Y ETIQUETA DE TIEMPO
        time_bar = QHBoxLayout()
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, int(self.max_duration * 100))
        self.time_slider.sliderMoved.connect(self.seek_video)
        
        self.time_label = QLabel(f"0.00s / {self.max_duration:.2f}s")
        self.time_label.setFixedWidth(120)
        
        time_bar.addWidget(self.time_slider)
        time_bar.addWidget(self.time_label)
        layout.addLayout(time_bar)

        # 4. CONTROLES
        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶ PLAY")
        self.play_btn.setFixedWidth(100)
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.btn_new = QPushButton("➕ Crear Segmento")
        self.btn_new.clicked.connect(self.create_segment)

        # Panel de edición de segmento seleccionado
        self.edit_frame = QFrame()
        self.edit_frame.setStyleSheet("background: #222; border-radius: 5px;")
        edit_ly = QHBoxLayout(self.edit_frame)
        
        self.in_start = QDoubleSpinBox(); self.in_start.setRange(0, self.max_duration)
        self.in_end = QDoubleSpinBox(); self.in_end.setRange(0, self.max_duration)
        self.in_zoom = QDoubleSpinBox(); self.in_zoom.setRange(1.1, 5.0); self.in_zoom.setValue(2.0)
        
        edit_ly.addWidget(QLabel("In:")); edit_ly.addWidget(self.in_start)
        edit_ly.addWidget(QLabel("Out:")); edit_ly.addWidget(self.in_end)
        edit_ly.addWidget(QLabel("Zoom:")); edit_ly.addWidget(self.in_zoom)
        
        btn_save = QPushButton("Actualizar")
        btn_save.clicked.connect(self.update_segment_values)
        edit_ly.addWidget(btn_save)
        
        self.edit_frame.setEnabled(False)

        controls.addWidget(self.play_btn)
        controls.addWidget(self.btn_new)
        controls.addWidget(self.edit_frame)
        layout.addLayout(controls)

        # 5. BOTÓN EXPORTAR (Corregido: Ahora se añade a la UI)
        self.btn_export = QPushButton("💾 EXPORTAR VIDEO FINAL")
        self.btn_export.setFixedHeight(45)
        self.btn_export.setStyleSheet("""
            QPushButton { 
                background-color: #28a745; 
                color: white; 
                font-weight: bold; 
                border-radius: 5px; 
                margin-top: 5px;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #444; }
        """)
        self.btn_export.clicked.connect(self.export)
        layout.addWidget(self.btn_export)

        self.setLayout(layout)
        self.update_preview()

    def create_segment(self):
        end_t = min(self.current_time + 2.0, self.max_duration)
        seg = self.composer.add_segment(self.current_time, end_t, 2.0)
        self.select_segment(seg)

    def select_segment(self, seg):
        self.selected_id = seg["id"]
        self.edit_frame.setEnabled(True)
        self.in_start.setValue(seg["start"])
        self.in_end.setValue(seg["end"])
        self.in_zoom.setValue(seg["zoom"])
        self.timeline_visual.update()

    def update_segment_values(self):
        for seg in self.composer.zoom_segments:
            if seg["id"] == self.selected_id:
                seg["start"] = self.in_start.value()
                seg["end"] = self.in_end.value()
                seg["zoom"] = self.in_zoom.value()
        self.update_preview()

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
        if self.current_time >= self.max_duration:
            self.current_time = 0; self.toggle_play(); return
        
        self.time_slider.setValue(int(self.current_time * 100))
        self.update_preview()

    def seek_video(self, val):
        self.current_time = val / 100.0
        if self.is_playing:
            self.play_start_time = time.perf_counter() - self.current_time
        self.update_preview()

    def update_preview(self):
        frame = self.composer.render_frame(self.current_time, preview_size=(854, 480))
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb.data, 854, 480, 854*3, QImage.Format.Format_RGB888).copy()
            self.video_label.setPixmap(QPixmap.fromImage(q_img))
        
        self.time_label.setText(f"{self.current_time:.2f}s / {self.max_duration:.2f}s")
        self.timeline_visual.update()

    def export(self):
        self.btn_export.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.btn_new.setEnabled(False)
        self.edit_frame.setEnabled(False)
        
        print("Iniciando exportación...")
        
        def progress_update(p):
            self.btn_export.setText(f"Exportando... {p}%")
            QApplication.processEvents() # Mantiene la ventana viva

        try:
            self.composer.export_video("resultado_final.mp4", progress_update)
            self.btn_export.setText("✅ ¡COMPLETADO!")
        except Exception as e:
            print(f"Error al exportar: {e}")
            self.btn_export.setText("❌ ERROR")
        
        QTimer.singleShot(3000, self.reset_export_button)

    def reset_export_button(self):
        self.btn_export.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.btn_new.setEnabled(True)
        self.btn_export.setText("💾 EXPORTAR VIDEO FINAL")

if __name__ == "__main__":
    app = QApplication(sys.argv); ex = FocusEditor(); ex.show(); sys.exit(app.exec())