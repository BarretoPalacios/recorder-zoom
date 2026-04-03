import cv2
import numpy as np
import dxcam
import pyautogui
import threading
from pynput import mouse
import time
import json

class TelemetryRecorder:
    _camera_instance = None

    def __init__(self, video_file="video_raw.mp4", json_file="telemetry.json"):
        if TelemetryRecorder._camera_instance is None:
            TelemetryRecorder._camera_instance = dxcam.create(output_color="BGR")
        
        self.camera = TelemetryRecorder._camera_instance
        self.video_file = video_file
        self.json_file = json_file
        
        self.is_recording = False
        self.sw, self.sh = pyautogui.size()
        
        # Estructura de datos para el JSON
        self.telemetry = {
            "info": {
                "screen_width": self.sw,
                "screen_height": self.sh,
                "date": time.ctime()
            },
            "events": []
        }
        self.is_clicking = False

    def _on_click(self, x, y, button, pressed):
        self.is_clicking = pressed

    def start(self):
        self.is_recording = True
        self.telemetry["events"] = []
        self.start_time = time.perf_counter()
        
        # Iniciar escucha de mouse
        self.listener = mouse.Listener(on_click=self._on_click)
        self.listener.start()
        
        # Iniciar hilos
        self.thread = threading.Thread(target=self._record_loop)
        self.thread.start()

    def stop(self):
        self.is_recording = False
        if hasattr(self, 'listener'): self.listener.stop()
        self.thread.join()
        self._save_telemetry()
        print(f"✅ Grabación finalizada. Archivos generados: {self.video_file} y {self.json_file}")

    def _record_loop(self):
        # Captura a 60 FPS (o lo máximo que dé el hardware)
        self.camera.start(target_fps=60)
        
        # Preparamos el escritor de video (Pantalla Completa, sin procesar)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(self.video_file, fourcc, 60.0, (self.sw, self.sh))

        while self.is_recording:
            frame = self.camera.get_latest_frame()
            if frame is None: continue
            
            # 1. Obtener datos del sistema
            mx, my = pyautogui.position()
            timestamp = time.perf_counter() - self.start_time
            
            # 2. Guardar Telemetría
            self.telemetry["events"].append({
                "t": round(timestamp, 4),
                "x": mx,
                "y": my,
                "c": self.is_clicking
            })
            
            # 3. Guardar el frame crudo (Sin zoom, sin recortes)
            out.write(frame)
            
            # Pequeña pausa para sincronizar con ~60fps
            time.sleep(1/120)

        out.release()
        self.camera.stop()

    def _save_telemetry(self):
        with open(self.json_file, 'w') as f:
            json.dump(self.telemetry, f, indent=2)