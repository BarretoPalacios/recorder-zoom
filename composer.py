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
        
        # Estado de la cámara
        self.smooth_x, self.smooth_y = self.sw // 2, self.sh // 2
        self.current_zoom = 1.0
        self.zoom_speed = 0.15 
        
        self.zoom_segments = [] 
        self.next_id = 0
        self.last_frame_idx = -1
        self.last_frame = None

    def add_segment(self, start, end, zoom):
        seg = {"id": self.next_id, "start": start, "end": end, "zoom": zoom}
        self.zoom_segments.append(seg)
        self.next_id += 1
        return seg

    def get_target_zoom(self, t):
        for seg in self.zoom_segments:
            if seg["start"] <= t <= seg["end"]:
                return seg["zoom"]
        return 1.0

    def render_frame(self, target_time, preview_size=None):
        events = self.telemetry["events"]
        
        # --- BÚSQUEDA BINARIA PARA VELOCIDAD REAL ---
        closest_idx = 0
        low, high = 0, len(events) - 1
        while low <= high:
            mid = (low + high) // 2
            if events[mid]["t"] < target_time: low = mid + 1
            else: closest_idx = mid; high = mid - 1

        # Solo leer si el frame cambió para no saturar el CPU
        if closest_idx != self.last_frame_idx:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, closest_idx)
            ret, frame = self.cap.read()
            if not ret or frame is None: return self.last_frame
            self.last_frame = frame
            self.last_frame_idx = closest_idx
        else:
            frame = self.last_frame

        if frame is None: return None

        # Suavizados
        tx, ty = events[closest_idx]["x"], events[closest_idx]["y"]
        self.smooth_x += (tx - self.smooth_x) * 0.1
        self.smooth_y += (ty - self.smooth_y) * 0.1
        
        target_z = self.get_target_zoom(target_time)
        self.current_zoom += (target_z - self.current_zoom) * self.zoom_speed

        # Renderizado FocusSee
        if self.current_zoom > 1.01:
            zw, zh = int(self.sw / self.current_zoom), int(self.sh / self.current_zoom)
            x1 = max(0, min(int(self.smooth_x - zw // 2), self.sw - zw))
            y1 = max(0, min(int(self.smooth_y - zh // 2), self.sh - zh))
            img = frame[y1:y1+zh, x1:x1+zw]
        else:
            img = frame

        canvas = np.zeros((self.sh, self.sw, 3), dtype=np.uint8)
        for i in range(self.sh):
            v = int(35 - (i / self.sh) * 15)
            canvas[i, :] = (v + 8, v, v) 
        
        h, w = img.shape[:2]; mask = np.zeros((h, w), dtype=np.uint8); r = 50
        cv2.rectangle(mask, (r, 0), (w-r, h), 255, -1)
        cv2.rectangle(mask, (0, r), (w, h-r), 255, -1)
        for p in [(r,r), (w-r,r), (r,h-r), (w-r,h-r)]: cv2.circle(mask, p, r, 255, -1)
        
        win = cv2.bitwise_and(img, img, mask=mask)
        nw, nh = int(self.sw * 0.85), int(self.sh * 0.85)
        win_res = cv2.resize(win, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
        mask_res = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_LANCZOS4)

        oy, ox = (self.sh - nh) // 2, (self.sw - nw) // 2
        region = canvas[oy:oy+nh, ox:ox+nw]
        bg_part = cv2.bitwise_and(region, region, mask=cv2.bitwise_not(mask_res))
        canvas[oy:oy+nh, ox:ox+nw] = cv2.add(win_res, bg_part)

        return cv2.resize(canvas, preview_size) if preview_size else canvas

    def export_video(self, output_name, progress_callback):
        # Resetear estado de la cámara para el inicio del video
        self.current_zoom = 1.0
        self.smooth_x, self.smooth_y = self.sw // 2, self.sh // 2
        self.last_frame_idx = -1
        
        max_duration = self.telemetry["events"][-1]["t"]
        fps = 30.0
        total_frames = int(max_duration * fps)
        
        # Configurar el codec y el archivo de salida
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_name, fourcc, fps, (self.sw, self.sh))
        
        for i in range(total_frames):
            current_t = i / fps
            # Renderizamos a resolución completa (sin preview_size)
            frame = self.render_frame(current_t, preview_size=None)
            
            if frame is not None:
                out.write(frame)
            
            # Actualizar progreso cada 10 frames para no ralentizar
            if i % 10 == 0:
                progress_callback(int((i / total_frames) * 100))
        
        out.release()
        print(f"✅ Video exportado con éxito: {output_name}")

    def __del__(self):
        if self.cap.isOpened(): self.cap.release()