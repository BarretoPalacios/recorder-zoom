import cv2
import json
import numpy as np

class VideoComposer:
    def __init__(self, video_path, json_path):
        self.video_path = video_path
        with open(json_path, 'r') as f:
            self.telemetry = json.load(f)
        
        self.cap = cv2.VideoCapture(video_path)
        self.sw = self.telemetry["info"]["screen_width"]
        self.sh = self.telemetry["info"]["screen_height"]
        
        self.last_frame_idx = -1
        self.last_frame = None
        
        # Suavizado de posición
        self.smooth_x = self.sw // 2
        self.smooth_y = self.sh // 2
        
        # --- NUEVO: Suavizado de Zoom ---
        self.current_zoom = 1.0  # Empieza en 1x (sin zoom)
        self.zoom_speed = 0.15   # Velocidad de la transición (0.1 a 0.2 es ideal)

    def render_frame(self, target_time, target_zoom_val=1.8, is_zoom_enabled=True, preview_size=None):
        events = self.telemetry["events"]
        
        # Búsqueda del evento por tiempo
        closest_idx = 0
        low, high = 0, len(events) - 1
        while low <= high:
            mid = (low + high) // 2
            if events[mid]["t"] < target_time:
                low = mid + 1
            else:
                closest_idx = mid
                high = mid - 1

        if closest_idx != self.last_frame_idx:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, closest_idx)
            ret, frame = self.cap.read()
            if not ret: return self.last_frame
            self.last_frame = frame
            self.last_frame_idx = closest_idx
        else:
            frame = self.last_frame

        if frame is None: return None

        # 1. SUAVIZADO DE POSICIÓN (X, Y)
        tx, ty = events[closest_idx]["x"], events[closest_idx]["y"]
        self.smooth_x += (tx - self.smooth_x) * 0.1
        self.smooth_y += (ty - self.smooth_y) * 0.1

        # 2. SUAVIZADO DE ZOOM (Transición fluida)
        # Si el zoom está apagado, el objetivo es 1.0. Si está prendido, es target_zoom_val.
        target_z = target_zoom_val if is_zoom_enabled else 1.0
        self.current_zoom += (target_z - self.current_zoom) * self.zoom_speed

        # Aplicar el recorte basado en el zoom actual suavizado
        # Si current_zoom es muy cercano a 1.0, usamos el frame completo
        if self.current_zoom > 1.01:
            zw, zh = int(self.sw / self.current_zoom), int(self.sh / self.current_zoom)
            x1 = max(0, min(int(self.smooth_x - zw // 2), self.sw - zw))
            y1 = max(0, min(int(self.smooth_y - zh // 2), self.sh - zh))
            display_img = frame[y1:y1+zh, x1:x1+zw]
        else:
            display_img = frame

        # 3. RENDERIZADO ESTÉTICO (Lienzo, fondo y bordes)
        canvas = np.zeros((self.sh, self.sw, 3), dtype=np.uint8)
        for i in range(self.sh):
            v = int(35 - (i / self.sh) * 15)
            canvas[i, :] = (v + 8, v, v) 

        h, w = display_img.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        radius = 50
        cv2.rectangle(mask, (radius, 0), (w - radius, h), 255, -1)
        cv2.rectangle(mask, (0, radius), (w, h - radius), 255, -1)
        cv2.circle(mask, (radius, radius), radius, 255, -1)
        cv2.circle(mask, (w - radius, radius), radius, 255, -1)
        cv2.circle(mask, (radius, h - radius), radius, 255, -1)
        cv2.circle(mask, (w - radius, h - radius), radius, 255, -1)

        win = cv2.bitwise_and(display_img, display_img, mask=mask)
        scale = 0.85
        nw, nh = int(self.sw * scale), int(self.sh * scale)
        win_res = cv2.resize(win, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
        mask_res = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_LANCZOS4)

        oy, ox = (self.sh - nh) // 2, (self.sw - nw) // 2
        region = canvas[oy:oy+nh, ox:ox+nw]
        bg_part = cv2.bitwise_and(region, region, mask=cv2.bitwise_not(mask_res))
        canvas[oy:oy+nh, ox:ox+nw] = cv2.add(win_res, bg_part)

        if preview_size:
            return cv2.resize(canvas, preview_size, interpolation=cv2.INTER_LINEAR)
        return canvas

    def export_video(self, output_name, zoom_val, is_zoom, smoothing, progress_callback):
        # Reiniciamos estados para el render final
        self.current_zoom = 1.0
        max_duration = self.telemetry["events"][-1]["t"]
        fps = 30.0
        total_frames = int(max_duration * fps)
        out = cv2.VideoWriter(output_name, cv2.VideoWriter_fourcc(*'mp4v'), fps, (self.sw, self.sh))
        
        for i in range(total_frames):
            frame = self.render_frame(i/fps, zoom_val, is_zoom)
            if frame is not None: out.write(frame)
            if i % 10 == 0: progress_callback(int((i / total_frames) * 100))
        out.release()