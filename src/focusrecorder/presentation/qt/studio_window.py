import os
import shutil
import platform
from pathlib import Path

import cv2
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor, QDesktopServices, QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QRadioButton, QSlider, QSpinBox, QVBoxLayout, QWidget

from ...application.errors import RecordingEnvironmentError
from ...app.factories.capture_backend_factory import create_capture_backend
from ...config.constants import UI_MAX_FPS, UI_MAX_SUAVIDAD, UI_MAX_ZOOM, UI_MIN_FPS, UI_MIN_SUAVIDAD, UI_MIN_ZOOM
from ...infrastructure.audio.sounddevice_audio import HAS_AUDIO
from .recording_presenter import DEFAULT_START_BUTTON_TEXT, RecordingPresenter

if HAS_AUDIO:
    import sounddevice as sd

if platform.system() == "Windows":
    import ctypes

    WDA_NONE = 0x0
    WDA_EXCLUDEFROMCAPTURE = 0x11


class FloatingPreviewWindow(QWidget):
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Recording Preview")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setFixedSize(360, 280)
        self.setStyleSheet(
            "QWidget{background:#0b1120;}QLabel#floatingPreview{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #020617,stop:1 #0f172a);color:#94a3b8;border:1px solid #334155;border-radius:14px;font-size:12px;font-weight:600;}"
            "QLabel#floatingTime{background:rgba(15,23,42,.55);color:white;border:1px solid rgba(255,255,255,.10);border-radius:12px;padding:6px 10px;font:700 14px Consolas;}"
            "QPushButton#floatingGhost{background:#172036;color:#f8fafc;border:1px solid #2c3d61;border-radius:12px;padding:8px 12px;font-size:11px;font-weight:800;}QPushButton#floatingGhost:hover{background:#223150;border:1px solid #3b4f78;}"
            "QPushButton#floatingDanger{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b91c1c,stop:1 #ef4444);color:white;border:none;border-radius:12px;padding:8px 12px;font-size:11px;font-weight:900;}QPushButton#floatingDanger:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #991b1b,stop:1 #dc2626);}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.addStretch(1)
        self.time_label = QLabel("00:00:00")
        self.time_label.setObjectName("floatingTime")
        top.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(top)
        self.preview_label = QLabel("Sin senal")
        self.preview_label.setObjectName("floatingPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_label, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.pause_btn = QPushButton("Pausar")
        self.pause_btn.setObjectName("floatingGhost")
        self.pause_btn.clicked.connect(self.pause_clicked.emit)
        actions.addWidget(self.pause_btn)
        self.stop_btn = QPushButton("Terminar")
        self.stop_btn.setObjectName("floatingDanger")
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        actions.addWidget(self.stop_btn)
        layout.addLayout(actions)

    def showEvent(self, event):
        super().showEvent(event)
        self._set_exclude_from_capture(True)

    def hideEvent(self, event):
        self._set_exclude_from_capture(False)
        super().hideEvent(event)

    def _set_exclude_from_capture(self, enabled):
        if platform.system() != "Windows":
            return
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(
                hwnd,
                WDA_EXCLUDEFROMCAPTURE if enabled else WDA_NONE,
            )
        except Exception:
            pass

    def position_bottom_right(self):
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            margin = 18
            self.move(
                available.right() - self.width() - margin,
                available.bottom() - self.height() - margin,
            )


class FocusApp(QWidget):
    hotkey_stop_requested = pyqtSignal()
    hotkey_pause_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.presenter = RecordingPresenter()
        self.recording_start_time = None
        self.render_thread = None
        self.floating_preview = FloatingPreviewWindow()
        self.floating_preview.pause_clicked.connect(self._handle_floating_pause)
        self.floating_preview.stop_clicked.connect(self._handle_floating_stop)
        self._idle_preview_backend = None
        self._compact_mode = False
        self._normal_geometry = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_recording_time)
        self.preview_timer = QTimer()
        self.preview_timer.setInterval(120)
        self.preview_timer.timeout.connect(self._update_preview)
        self._disk_tick = 0
        self.hotkey_stop_requested.connect(self._handle_hotkey_stop)
        self.hotkey_pause_changed.connect(self._handle_hotkey_pause_changed)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Focus Recorder Studio")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(1040, 690)
        self.setMinimumSize(980, 650)
        self.setObjectName("root")
        self.setStyleSheet(
            "QWidget#root{background:#0f172a;}QFrame#shell{background:#0f172a;border:none;}"
            "QFrame#sidebar{background:#131c31;border:none;border-radius:0px;}QFrame#content{background:#0b1020;border:none;border-radius:0px;}"
            "QFrame#card{background:#10182b;border:1px solid #24314f;border-radius:18px;}QFrame#previewCard{background:#0b1120;border:1px solid #243044;border-radius:18px;}"
            "QLabel{color:#e7edf9;}QLabel#heroTitle{color:white;font-size:24px;font-weight:800;}QLabel#heroSub{color:#cbd5e1;font-size:11px;}"
            "QLabel#badge{background:rgba(255,255,255,.10);color:#e2e8f0;border:1px solid rgba(255,255,255,.10);border-radius:10px;padding:5px 8px;font-size:10px;font-weight:700;}"
            "QLabel#sidebarTitle{color:#f8fafc;font-size:22px;font-weight:800;}QLabel#sidebarCopy{color:#8ea0c8;font-size:11px;}"
            "QLabel#metric{background:#18233f;color:white;border:1px solid #233354;border-radius:14px;padding:9px;font-size:10px;}"
            "QLabel#time{background:rgba(15,23,42,.45);color:white;border:1px solid rgba(255,255,255,.10);border-radius:13px;padding:7px 10px;font:700 16px Consolas;}"
            "QLabel#section{color:#f8fafc;font-size:14px;font-weight:800;}QLabel#field{color:#d6e1fb;font-size:10px;font-weight:800;}QLabel#helper{color:#8ea0c8;font-size:10px;}QLabel#path{background:#111827;border:1px solid #2a3a59;border-radius:14px;padding:10px;color:#e7edf9;}"
            "QLabel#preview{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #020617,stop:1 #0f172a);color:#94a3b8;border:1px solid #334155;border-radius:14px;font-size:12px;font-weight:600;}"
            "QLabel#status{padding:8px 10px;border-radius:14px;font-size:11px;font-weight:700;}QLineEdit,QSpinBox,QComboBox{background:#0f172a;border:1px solid #2a3a59;border-radius:14px;padding:8px 10px;font-size:11px;min-height:16px;color:#f8fafc;}QLineEdit:focus,QSpinBox:focus,QComboBox:focus{border:1px solid #f97316;}"
            "QPushButton{border:none;border-radius:14px;padding:8px 12px;font-size:11px;font-weight:800;}QPushButton#ghost{background:#172036;color:#f8fafc;border:1px solid #2c3d61;}QPushButton#ghost:hover{background:#223150;border:1px solid #3b4f78;}"
            "QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff4141,stop:1 #ff7a18);color:white;font-size:13px;font-weight:900;}QPushButton#primary:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #eb2f2f,stop:1 #f97316);}"
            "QPushButton:disabled{background:#dbe3ef;color:#94a3b8;}QRadioButton{background:#172036;color:#e7edf9;border:1px solid #2c3d61;border-radius:16px;padding:8px 9px;font-size:11px;font-weight:800;}QRadioButton:hover{border:1px solid #fdba74;background:#223150;}QRadioButton:checked{background:#fff7ed;border:1px solid #f97316;color:#c2410c;}QRadioButton::indicator{width:0;height:0;}"
            "QRadioButton#chip{padding:8px 14px;border-radius:14px;min-width:58px;font-size:10px;font-weight:900;text-align:center;}QRadioButton#chip:hover{border:1px solid #fdba74;background:#21304d;}QRadioButton#chip:checked{background:#ffedd5;border:1px solid #fb923c;color:#9a3412;}QRadioButton#chip:disabled{background:#111827;color:#64748b;border:1px solid #24314f;}"
            "QCheckBox{font-size:11px;font-weight:700;}QSlider::groove:horizontal{background:#dbe3ef;height:7px;border-radius:4px;}QSlider::sub-page:horizontal{background:#0f766e;border-radius:4px;}QSlider::handle:horizontal{background:white;border:2px solid #0f766e;width:16px;height:16px;margin:-5px 0;border-radius:8px;}QProgressBar{background:#e2e8f0;border:none;border-radius:8px;min-height:9px;}QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0f766e,stop:1 #22c55e);border-radius:8px;}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("shell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        root.addWidget(shell)

        ui = self.presenter.get_default_ui_state()

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 14)
        sidebar_layout.setSpacing(7)
        rec_badge = QLabel("REC")
        rec_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rec_badge.setFixedSize(40, 40)
        rec_badge.setStyleSheet("background:#ff6b2c;color:white;border-radius:14px;font-size:18px;font-weight:800;")
        sidebar_layout.addWidget(rec_badge, 0, Qt.AlignmentFlag.AlignLeft)
        sidebar_title = QLabel("Focus Recorder")
        sidebar_title.setObjectName("sidebarTitle")
        sidebar_layout.addWidget(sidebar_title)
        sidebar_copy = QLabel("Studio de grabacion para cursor, vertical, full screen y render dual.")
        sidebar_copy.setObjectName("sidebarCopy")
        sidebar_copy.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_copy)
        self.header_badge = QLabel("LISTO")
        self.header_badge.setObjectName("badge")
        sidebar_layout.addWidget(self.header_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.time_counter = QLabel("00:00:00")
        self.time_counter.setObjectName("time")
        sidebar_layout.addWidget(self.time_counter, 0, Qt.AlignmentFlag.AlignLeft)
        hotkeys = QLabel("F7 pausa o reanuda\nF10 termina y renderiza\nLa ventana se minimiza al grabar")
        hotkeys.setObjectName("sidebarCopy")
        hotkeys.setWordWrap(True)
        sidebar_layout.addWidget(hotkeys)
        self.mode_summary_label = QLabel("Salida\n--")
        self.mode_summary_label.setObjectName("metric")
        self.quality_summary_label = QLabel("Calidad\n--")
        self.quality_summary_label.setObjectName("metric")
        self.disk_label = QLabel("Disco\n--")
        self.disk_label.setObjectName("metric")
        sidebar_layout.addWidget(self.mode_summary_label)
        sidebar_layout.addWidget(self.quality_summary_label)
        sidebar_layout.addWidget(self.disk_label)
        sidebar_layout.addStretch(1)
        shell_layout.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(2)
        shell_layout.addWidget(content, 1)

        header = QFrame()
        self.header_section = header
        header.setStyleSheet("background:transparent;border:none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_text = QVBoxLayout()
        title = QLabel("Sistema de captura")
        title.setObjectName("heroTitle")
        header_text.addWidget(title)
        sub = QLabel("Enfocado a la grabacion del cursor + seguimiento")
        sub.setObjectName("heroSub")
        header_text.addWidget(sub)
        header_layout.addLayout(header_text, 1)
        self.preview_mode_label = QLabel("Cursor-first Studio")
        self.preview_mode_label.setObjectName("badge")
        header_layout.addWidget(self.preview_mode_label, 0, Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(header)

        self.status = QLabel()
        self.status_section = self.status
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status.setWordWrap(True)
        content_layout.addWidget(self.status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        content_layout.addWidget(self.progress_bar)

        canvas = QWidget()
        self.scroll_section = canvas
        content_layout.addWidget(canvas, 1)
        body = QGridLayout(canvas)
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(6)
        body.setVerticalSpacing(3)
        body.setColumnStretch(0, 1)
        body.setColumnStretch(1, 1)

        dest = QFrame()
        dest.setObjectName("card")
        dest_l = QVBoxLayout(dest)
        dest_l.setContentsMargins(10, 10, 10, 10)
        dest_l.setSpacing(5)
        label = QLabel("Destino y nombre")
        label.setObjectName("section")
        dest_l.addWidget(label)
        row = QHBoxLayout()
        self.dir_label = QLabel(self._get_video_directory_display())
        self.dir_label.setObjectName("path")
        self.dir_label.setWordWrap(True)
        row.addWidget(self.dir_label, 1)
        self.change_dir_btn = QPushButton("Cambiar")
        self.change_dir_btn.setObjectName("ghost")
        self.change_dir_btn.clicked.connect(self._change_output_directory)
        row.addWidget(self.change_dir_btn)
        dest_l.addLayout(row)
        name_label = QLabel("Nombre del video")
        name_label.setObjectName("field")
        dest_l.addWidget(name_label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej: tutorial_demo  |  vacio = automatico")
        dest_l.addWidget(self.name_input)
        body.addWidget(dest, 0, 0)

        record = QFrame()
        record.setObjectName("card")
        record_l = QVBoxLayout(record)
        record_l.setContentsMargins(10, 10, 10, 10)
        record_l.setSpacing(5)
        sec = QLabel("Formato y camara")
        sec.setObjectName("section")
        record_l.addWidget(sec)
        self.export_group = QButtonGroup(self)
        mode_row = QHBoxLayout()
        self.radio_full = QRadioButton("16:9\nPantalla completa")
        self.radio_tiktok = QRadioButton("9:16\nTikTok vertical")
        self.radio_both = QRadioButton("Dual\nAmbos formatos")
        self.export_group.addButton(self.radio_full, 0)
        self.export_group.addButton(self.radio_tiktok, 1)
        self.export_group.addButton(self.radio_both, 2)
        self.export_group.buttonClicked.connect(self._update_mode_summary)
        if ui["export_mode"] == "full":
            self.radio_full.setChecked(True)
        elif ui["export_mode"] == "tiktok":
            self.radio_tiktok.setChecked(True)
        else:
            self.radio_both.setChecked(True)
        mode_row.addWidget(self.radio_full)
        mode_row.addWidget(self.radio_tiktok)
        mode_row.addWidget(self.radio_both)
        record_l.addLayout(mode_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(0, 1)

        zoom_label = QLabel("Zoom")
        zoom_label.setObjectName("field")
        grid.addWidget(zoom_label, 0, 0)
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(UI_MIN_ZOOM, UI_MAX_ZOOM)
        self.zoom_spin.setValue(ui["zoom"])
        self.zoom_spin.setPrefix("x ")
        self.zoom_spin.setSingleStep(2)
        self.zoom_spin.setVisible(False)
        self.zoom_spin.valueChanged.connect(self._sync_zoom_preset)
        self.zoom_group = QButtonGroup(self)
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(8)
        for label, value in (("x1.0", 10), ("x1.8", 18), ("x2.5", 25), ("x3.0", 30)):
            btn = QRadioButton(label)
            btn.setObjectName("chip")
            btn.value = value
            self.zoom_group.addButton(btn)
            zoom_row.addWidget(btn)
        zoom_row.addStretch(1)
        self.zoom_group.buttonClicked.connect(self._apply_zoom_preset)
        grid.addLayout(zoom_row, 1, 0)

        fps_label = QLabel("FPS")
        fps_label.setObjectName("field")
        grid.addWidget(fps_label, 2, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(UI_MIN_FPS, UI_MAX_FPS)
        self.fps_spin.setValue(ui["fps"])
        self.fps_spin.setVisible(False)
        self.fps_spin.valueChanged.connect(self._sync_fps_preset)
        self.fps_group = QButtonGroup(self)
        fps_row = QHBoxLayout()
        fps_row.setSpacing(8)
        for label, value in (("24", 24), ("30", 30), ("60", 60)):
            btn = QRadioButton(label)
            btn.setObjectName("chip")
            btn.value = value
            self.fps_group.addButton(btn)
            fps_row.addWidget(btn)
        fps_row.addStretch(1)
        self.fps_group.buttonClicked.connect(self._apply_fps_preset)
        grid.addLayout(fps_row, 3, 0)

        render_quality_label = QLabel("Render")
        render_quality_label.setObjectName("field")
        grid.addWidget(render_quality_label, 4, 0)
        self.render_quality_combo = QComboBox()
        self.render_quality_combo.addItem("Rapida", "fast")
        self.render_quality_combo.addItem("Normal", "normal")
        self.render_quality_combo.addItem("Alta", "high")
        current_render_quality = ui.get("render_quality", "normal")
        idx = self.render_quality_combo.findData(current_render_quality)
        self.render_quality_combo.setCurrentIndex(max(idx, 0))
        self.render_quality_combo.setVisible(False)
        self.render_quality_combo.currentIndexChanged.connect(self._sync_render_quality_preset)
        self.render_quality_group = QButtonGroup(self)
        render_row = QHBoxLayout()
        render_row.setSpacing(8)
        for label, value in (("Rapida", "fast"), ("Normal", "normal"), ("Alta", "high")):
            btn = QRadioButton(label)
            btn.setObjectName("chip")
            btn.value = value
            self.render_quality_group.addButton(btn)
            render_row.addWidget(btn)
        render_row.addStretch(1)
        self.render_quality_group.buttonClicked.connect(self._apply_render_quality_preset)
        grid.addLayout(render_row, 5, 0)
        smooth_label = QLabel("Suavidad")
        smooth_label.setObjectName("field")
        grid.addWidget(smooth_label, 6, 0)
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(UI_MIN_SUAVIDAD, UI_MAX_SUAVIDAD)
        self.smooth_slider.setValue(ui["suavidad"])
        self.smooth_slider.valueChanged.connect(self._update_mode_summary)
        grid.addWidget(self.smooth_slider, 7, 0)
        self.smooth_value_label = QLabel()
        self.smooth_value_label.setObjectName("helper")
        grid.addWidget(self.smooth_value_label, 8, 0)
        self.preview_quality_label = QLabel()
        self.preview_quality_label.setObjectName("helper")
        self.preview_quality_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.preview_quality_label, 9, 0)
        record_l.addLayout(grid)
        body.addWidget(record, 0, 1)

        preview = QFrame()
        preview.setObjectName("previewCard")
        preview_l = QVBoxLayout(preview)
        preview_l.setContentsMargins(10, 10, 10, 10)
        preview_l.setSpacing(5)
        sec = QLabel("Vista previa")
        sec.setObjectName("section")
        sec.setStyleSheet("color:white;")
        preview_l.addWidget(sec)
        self.preview_label = QLabel("Sin senal")
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(156)
        self.preview_label.setMaximumHeight(170)
        preview_l.addWidget(self.preview_label)
        foot = QHBoxLayout()
        self.preview_hint_label = QLabel("Preview nitido y suavizado dentro de la ventana.")
        self.preview_hint_label.setObjectName("helper")
        self.preview_hint_label.setStyleSheet("color:#cbd5e1;")
        foot.addWidget(self.preview_hint_label, 1)
        self.preview_chip = QLabel("--")
        self.preview_chip.setObjectName("badge")
        foot.addWidget(self.preview_chip, 0, Qt.AlignmentFlag.AlignRight)
        preview_l.addLayout(foot)
        body.addWidget(preview, 1, 0)

        actions = QFrame()
        actions.setObjectName("card")
        actions_l = QVBoxLayout(actions)
        actions_l.setContentsMargins(10, 10, 10, 10)
        actions_l.setSpacing(5)
        actions_title = QLabel("Iniciar grabacion")
        actions_title.setObjectName("section")
        actions_l.addWidget(actions_title)

        self.audio_checkbox = QCheckBox("Capturar microfono")
        self.audio_checkbox.setEnabled(HAS_AUDIO)
        if not HAS_AUDIO:
            self.audio_checkbox.setText("Capturar microfono (instala sounddevice)")
        self.audio_checkbox.setChecked(ui["audio"])
        self.audio_checkbox.toggled.connect(self._handle_audio_toggle)
        actions_l.addWidget(self.audio_checkbox)

        self.audio_device_combo = QComboBox()
        self.audio_device_combo.setVisible(False)
        if HAS_AUDIO:
            self.audio_device_combo.addItem("Dispositivo por defecto", None)
            try:
                for index, device in enumerate(sd.query_devices()):
                    if device["max_input_channels"] > 0:
                        self.audio_device_combo.addItem(device["name"], index)
            except Exception:
                pass
        actions_l.addWidget(self.audio_device_combo)

        self.vu_meter = QProgressBar()
        self.vu_meter.setRange(0, 100)
        self.vu_meter.setValue(0)
        self.vu_meter.setTextVisible(False)
        self.vu_meter.setFixedHeight(10)
        self.vu_meter.setVisible(False)
        actions_l.addWidget(self.vu_meter)

        tools = QHBoxLayout()
        tools.setSpacing(5)
        self.open_folder_btn = QPushButton("Abrir carpeta")
        self.open_folder_btn.setObjectName("ghost")
        self.open_folder_btn.setFixedHeight(30)
        self.open_folder_btn.clicked.connect(self.presenter.reveal_output_directory)
        tools.addWidget(self.open_folder_btn)
        self.open_last_btn = QPushButton("Mostrar ultimo")
        self.open_last_btn.setObjectName("ghost")
        self.open_last_btn.setFixedHeight(30)
        self.open_last_btn.setEnabled(False)
        self.open_last_btn.clicked.connect(self.presenter.reveal_last_export)
        tools.addWidget(self.open_last_btn)
        self.play_last_btn = QPushButton("Reproducir")
        self.play_last_btn.setObjectName("ghost")
        self.play_last_btn.setFixedHeight(30)
        self.play_last_btn.setEnabled(False)
        self.play_last_btn.clicked.connect(self._play_last_export)
        tools.addWidget(self.play_last_btn)
        actions_l.addLayout(tools)
        self.btn = QPushButton(DEFAULT_START_BUTTON_TEXT)
        self.btn.setObjectName("primary")
        self.btn.setFixedHeight(40)
        self.btn.clicked.connect(self.toggle)
        actions_l.addWidget(self.btn)
        body.addWidget(actions, 1, 1)

        self._handle_audio_toggle(ui["audio"])
        self._sync_zoom_preset(self.zoom_spin.value())
        self._sync_fps_preset(self.fps_spin.value())
        self._sync_render_quality_preset(self.render_quality_combo.currentIndex())

        self._update_mode_summary()
        self._update_disk_info()
        self._update_status_text("Listo para grabar", self._success_status_style())
        self._center_on_screen()
        self._start_idle_preview()

    def _get_video_directory_display(self):
        return self.presenter.get_output_dir_display()

    def _get_export_mode(self):
        return {0: "full", 1: "tiktok", 2: "both"}[self.export_group.checkedId()]

    def _set_controls_enabled(self, enabled):
        for widget in (self.zoom_spin, self.smooth_slider, self.fps_spin, self.render_quality_combo, self.radio_full, self.radio_tiktok, self.radio_both, self.change_dir_btn, self.name_input, self.audio_checkbox, self.audio_device_combo):
            widget.setEnabled(enabled)
        for button in self.zoom_group.buttons():
            button.setEnabled(enabled)
        for button in self.fps_group.buttons():
            button.setEnabled(enabled)
        for button in self.render_quality_group.buttons():
            button.setEnabled(enabled)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = self.frameGeometry()
            geo.moveCenter(screen.availableGeometry().center())
            self.move(geo.topLeft())

    def _handle_audio_toggle(self, checked):
        self.audio_device_combo.setVisible(checked and HAS_AUDIO)
        self.vu_meter.setVisible(checked and self.presenter.has_active_recording())

    def _apply_zoom_preset(self, button):
        self.zoom_spin.setValue(button.value)
        self._update_mode_summary()

    def _sync_zoom_preset(self, value):
        checked = False
        for button in self.zoom_group.buttons():
            if getattr(button, "value", None) == value:
                button.setChecked(True)
                checked = True
                break
        if not checked and self.zoom_group.buttons():
            self.zoom_group.buttons()[0].setChecked(True)
        self._update_mode_summary()

    def _apply_fps_preset(self, button):
        self.fps_spin.setValue(button.value)
        self._update_mode_summary()

    def _sync_fps_preset(self, value):
        checked = False
        for button in self.fps_group.buttons():
            if getattr(button, "value", None) == value:
                button.setChecked(True)
                checked = True
                break
        if not checked and self.fps_group.buttons():
            self.fps_group.buttons()[0].setChecked(True)
        self._update_mode_summary()

    def _apply_render_quality_preset(self, button):
        idx = self.render_quality_combo.findData(button.value)
        self.render_quality_combo.setCurrentIndex(max(idx, 0))
        self._update_mode_summary()

    def _sync_render_quality_preset(self, _index):
        current = self.render_quality_combo.currentData()
        checked = False
        for button in self.render_quality_group.buttons():
            if getattr(button, "value", None) == current:
                button.setChecked(True)
                checked = True
                break
        if not checked and self.render_quality_group.buttons():
            self.render_quality_group.buttons()[0].setChecked(True)
        self._update_mode_summary()

    def _update_status_text(self, text, style):
        self.status.setText(text)
        self.status.setStyleSheet(style)

    def _update_mode_summary(self):
        mode = self._get_export_mode()
        label = {"full": "16:9 full", "tiktok": "9:16 vertical", "both": "Full + TikTok"}[mode]
        render_quality = self.render_quality_combo.currentData()
        render_label = {"fast": "Rapida", "normal": "Normal", "high": "Alta"}[render_quality]
        self.mode_summary_label.setText(f"Salida\n{label}")
        self.quality_summary_label.setText(f"Render\n{self.fps_spin.value()} FPS | {render_label}")
        self.smooth_value_label.setText(f"Seguimiento suave: {self.smooth_slider.value()} / {UI_MAX_SUAVIDAD}")
        self.preview_quality_label.setText(f"Preview {render_label.lower()} a {self.fps_spin.value()} FPS.")
        self.preview_mode_label.setText(label)
        self.preview_chip.setText({"full": "Full", "tiktok": "TikTok", "both": "Dual"}[mode])
        if mode == "both":
            self.preview_hint_label.setText("Vista completa con guia interna del encuadre TikTok.")
        elif mode == "tiktok":
            self.preview_hint_label.setText("Vista vertical enfocada al encuadre 9:16.")
        else:
            self.preview_hint_label.setText("Vista completa del encuadre principal.")

    def _update_recording_time(self):
        recorder = self.presenter.recorder
        if recorder is not None and recorder.is_recording:
            elapsed = recorder.get_elapsed_time()
            text = f"{int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}:{int(elapsed % 60):02d}"
            self.time_counter.setText(text)
            self.floating_preview.time_label.setText(text)

    def _change_output_directory(self):
        current_dir = self.presenter.get_output_dir_display()
        new_dir = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de destino para videos", current_dir, QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)
        if new_dir:
            self.presenter.update_output_directory(Path(new_dir))
            self.dir_label.setText(self.presenter.get_output_dir_display())
            self._update_status_text(f"Carpeta actualizada\n{Path(new_dir).name}", self._success_status_style())
            self._update_disk_info()

    def toggle(self):
        if not self.presenter.has_active_recording():
            self._set_controls_enabled(False)
            self._stop_idle_preview()
            try:
                view_model = self.presenter.start_recording(zoom=self.zoom_spin.value(), suavidad=self.smooth_slider.value(), fps=self.fps_spin.value(), custom_name=self.name_input.text().strip(), audio=self.audio_checkbox.isChecked(), audio_device=self.audio_device_combo.currentData() if self.audio_checkbox.isChecked() else None, render_quality=self.render_quality_combo.currentData())
            except RecordingEnvironmentError as exc:
                self._set_controls_enabled(True)
                self._start_idle_preview()
                self._update_status_text(f"Error al iniciar\n{exc}", self._error_status_style())
                return
            except Exception as exc:
                self._set_controls_enabled(True)
                self._start_idle_preview()
                self._update_status_text(f"Error inesperado\n{exc}", self._error_status_style())
                return
            self.recording_start_time = True
            self.timer.start(100)
            self.preview_timer.setInterval(33)
            self.preview_timer.start()
            self.time_counter.setVisible(True)
            self.vu_meter.setVisible(self.audio_checkbox.isChecked())
            self.btn.setText(view_model.button_text)
            self.btn.setStyleSheet(self._stop_button_style())
            self.presenter.recorder.on_pause_toggled = self.hotkey_pause_changed.emit
            self.presenter.recorder.on_stop_requested = self.hotkey_stop_requested.emit
            self.header_badge.setText("REC EN CURSO")
            self._update_status_text(f"{view_model.status_text}\nF7 pausa o reanuda  |  F10 termina", self._recording_status_style())
            self._enter_compact_recording_mode()
            return

        self.timer.stop()
        self.preview_timer.stop()
        self.setUpdatesEnabled(False)
        self.vu_meter.setVisible(False)
        self.preview_label.clear()
        self.preview_label.setText("Procesando video...")
        self.time_counter.setVisible(False)
        self.recording_start_time = None
        self.btn.setEnabled(False)
        mode = self._get_export_mode()
        self.presenter.save_current_preferences(zoom=self.zoom_spin.value(), suavidad=self.smooth_slider.value(), fps=self.fps_spin.value(), export_mode=mode, render_quality=self.render_quality_combo.currentData())
        render_view_model = self.presenter.build_rendering_view_model(mode)
        self._update_status_text(render_view_model.status_text, self._rendering_status_style())
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.header_badge.setText("RENDERIZANDO")
        self._exit_compact_recording_mode()
        self.setUpdatesEnabled(True)
        self.update()
        self.repaint()
        try:
            self.presenter.prepare_stop_recording()
        except Exception as exc:
            self.setUpdatesEnabled(True)
            self.progress_bar.setVisible(False)
            self.btn.setEnabled(True)
            self.btn.setText("DETENER Y PROCESAR")
            self.btn.setStyleSheet(self._stop_button_style())
            self._update_status_text(f"Error al detener\n{exc}", self._error_status_style())
            return
        from . import main_window as main_window_module

        self.render_thread = main_window_module.RenderThread(self.presenter, export_mode=mode)
        self.render_thread.progress.connect(self.progress_bar.setValue)
        self.render_thread.finished.connect(self.on_finished)
        self.render_thread.start()

    def on_finished(self, result):
        self.timer.stop()
        self.preview_timer.stop()
        self.time_counter.setVisible(False)
        self.recording_start_time = None
        self.btn.setEnabled(True)
        view_model = self.presenter.build_finished_view_model(result)
        self.btn.setText(view_model.button_text)
        self.btn.setStyleSheet(self._start_button_style())
        self._update_status_text(view_model.status_text, self._success_status_style())
        self.progress_bar.setVisible(False)
        self.preview_label.clear()
        self.preview_label.setText("Sin senal")
        self.header_badge.setText("LISTO")
        self.preview_hint_label.setText("Preview nitido y suavizado dentro de la ventana.")
        self._set_controls_enabled(True)
        self._update_disk_info()
        has_output = bool(view_model.primary_path)
        self.open_last_btn.setEnabled(has_output)
        self.play_last_btn.setEnabled(has_output)
        self.presenter.reveal_output_directory()
        self.preview_timer.setInterval(120)
        self.preview_timer.start()
        self._start_idle_preview()

    def _handle_hotkey_stop(self):
        if self.presenter.has_active_recording() and self.btn.isEnabled():
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.toggle()

    def _handle_hotkey_pause_changed(self, paused):
        if paused:
            self.header_badge.setText("PAUSADO")
            self._update_status_text("Grabacion en pausa\nF7 reanuda  |  F10 termina", self._rendering_status_style())
            self.preview_hint_label.setText("Captura pausada. El ultimo frame queda congelado.")
            self.floating_preview.pause_btn.setText("Reanudar")
        else:
            self.header_badge.setText("REC EN CURSO")
            self._update_status_text("Grabando ahora\nF7 pausa o reanuda  |  F10 termina", self._recording_status_style())
            self.preview_hint_label.setText("Preview nitido y suavizado dentro de la ventana.")
            self.floating_preview.pause_btn.setText("Pausar")

    def _update_preview(self):
        recorder = self.presenter.recorder
        mode = self._get_export_mode()
        if recorder is not None:
            frame = self._build_preview_frame(recorder, mode)
        else:
            frame = self._build_idle_preview_frame(mode)
        if frame is not None:
            height, width, channels = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = QImage(rgb.data, width, height, width * channels, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(image).scaled(self.preview_label.width(), self.preview_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(pixmap)
            if self.floating_preview.isVisible():
                floating_pixmap = QPixmap.fromImage(image).scaled(self.floating_preview.preview_label.width(), self.floating_preview.preview_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.floating_preview.preview_label.setPixmap(floating_pixmap)
        if self.audio_checkbox.isChecked():
            self.vu_meter.setValue(recorder.audio_level if recorder is not None else 0)
        self._disk_tick += 1
        if self._disk_tick >= 15:
            self._disk_tick = 0
            self._update_disk_info()

    def _build_preview_frame(self, recorder, mode):
        if mode == "tiktok":
            frame = recorder.session.latest_frame
            if frame is None:
                return None
            return self._build_tiktok_preview(frame.copy(), recorder.session.latest_mx, recorder.session.latest_my, recorder.settings.zoom)
        if mode == "both":
            frame = recorder.session.latest_frame
            if frame is None:
                return None
            return self._draw_tiktok_guide(frame.copy(), recorder)
        return recorder.session.latest_frame

    def _draw_tiktok_guide(self, frame, recorder):
        sh, sw = frame.shape[:2]
        zoom_value = max(recorder.settings.zoom, 1.0)
        center_x = recorder.session.latest_mx or sw // 2
        center_y = recorder.session.latest_my or sh // 2
        crop_h = min(int(sh / zoom_value), sh)
        crop_w = min(int(crop_h * 9 / 16), sw)
        x1 = int(max(min(center_x - crop_w // 2, sw - crop_w), 0))
        y1 = int(max(min(center_y - crop_h // 2, sh - crop_h), 0))
        x2 = x1 + crop_w
        y2 = y1 + crop_h

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (sw, sh), (6, 10, 22), thickness=-1)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 255, 255), thickness=-1)
        frame = cv2.addWeighted(overlay, 0.16, frame, 0.84, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (56, 189, 248), thickness=2)
        cv2.putText(
            frame,
            "TikTok",
            (x1 + 8, max(y1 + 22, 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (56, 189, 248),
            2,
            cv2.LINE_AA,
        )
        return frame

    def _build_idle_preview_frame(self, mode):
        backend = self._ensure_idle_preview_backend()
        if backend is None:
            return None
        try:
            frame = backend.capture_frame()
        except Exception:
            self._stop_idle_preview()
            return None
        if frame is None:
            return None
        cursor = QCursor.pos()
        center_x = cursor.x()
        center_y = cursor.y()
        zoom_value = self.zoom_spin.value() / 10.0
        if mode == "tiktok":
            return self._build_tiktok_preview(frame, center_x, center_y, zoom_value)
        if mode == "both":
            return self._draw_tiktok_guide_for_values(frame, center_x, center_y, zoom_value)
        return frame

    def _build_tiktok_preview(self, frame, center_x, center_y, zoom_value):
        sh, sw = frame.shape[:2]
        crop_h = min(int(sh / max(zoom_value, 1.0)), sh)
        crop_w = min(int(crop_h * 9 / 16), sw)
        x1 = int(max(min(center_x - crop_w // 2, sw - crop_w), 0))
        y1 = int(max(min(center_y - crop_h // 2, sh - crop_h), 0))
        cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
        if cropped.size == 0:
            return frame
        return cv2.resize(cropped, (crop_w, sh), interpolation=cv2.INTER_LINEAR)

    def _draw_tiktok_guide_for_values(self, frame, center_x, center_y, zoom_value):
        class _PreviewRecorder:
            pass

        preview = _PreviewRecorder()
        preview.settings = type("Settings", (), {"zoom": zoom_value})()
        preview.session = type(
            "Session",
            (),
            {"latest_mx": center_x, "latest_my": center_y},
        )()
        return self._draw_tiktok_guide(frame, preview)

    def _ensure_idle_preview_backend(self):
        if self._idle_preview_backend is None:
            try:
                self._idle_preview_backend = create_capture_backend(
                    is_windows=platform.system() == "Windows"
                )
                self._idle_preview_backend.start()
            except Exception:
                self._idle_preview_backend = None
        return self._idle_preview_backend

    def _start_idle_preview(self):
        self._ensure_idle_preview_backend()
        if not self.preview_timer.isActive():
            self.preview_timer.setInterval(120)
            self.preview_timer.start()

    def _stop_idle_preview(self):
        if self._idle_preview_backend is not None:
            try:
                self._idle_preview_backend.stop()
            except Exception:
                pass
        self._idle_preview_backend = None

    def _enter_compact_recording_mode(self):
        if self._compact_mode:
            return
        self._compact_mode = True
        self._normal_geometry = self.geometry()
        self.floating_preview.pause_btn.setText("Pausar")
        self.floating_preview.pause_btn.setEnabled(True)
        self.floating_preview.stop_btn.setEnabled(True)
        self.floating_preview.position_bottom_right()
        self.floating_preview.show()
        self.hide()

    def _exit_compact_recording_mode(self):
        if not self._compact_mode:
            return
        self._compact_mode = False
        self.floating_preview.preview_label.clear()
        self.floating_preview.preview_label.setText("Sin senal")
        self.floating_preview.time_label.setText("00:00:00")
        self.floating_preview.pause_btn.setText("Pausar")
        self.floating_preview.pause_btn.setEnabled(True)
        self.floating_preview.stop_btn.setEnabled(True)
        self.floating_preview.hide()
        self.floating_preview.close()
        if self._normal_geometry is not None:
            self.setGeometry(self._normal_geometry)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _handle_floating_pause(self):
        recorder = self.presenter.recorder
        if recorder is None or not recorder.is_recording:
            return
        paused = recorder.toggle_pause()
        self._handle_hotkey_pause_changed(paused)

    def _handle_floating_stop(self):
        if self.presenter.has_active_recording() and self.btn.isEnabled():
            self.floating_preview.pause_btn.setEnabled(False)
            self.floating_preview.stop_btn.setEnabled(False)
            QTimer.singleShot(0, self.toggle)

    def _update_disk_info(self):
        output_dir = self.presenter.get_output_dir_display()
        drive = os.path.splitdrive(output_dir)[0] or "/"
        try:
            free_gb = shutil.disk_usage(drive).free / 1024 ** 3
        except OSError:
            free_gb = 0.0
        temp_mb = 0.0
        recorder = self.presenter.recorder
        if recorder is not None and recorder._temp_path:
            try:
                temp_mb = os.path.getsize(recorder._temp_path) / 1024 ** 2
            except OSError:
                pass
        self.disk_label.setText(f"Disco\n{free_gb:.1f} GB libres" if temp_mb <= 0 else f"Disco\n{free_gb:.1f} GB libres | temp {temp_mb:.0f} MB")

    def _play_last_export(self):
        target = self.presenter.get_last_export_path()
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    @staticmethod
    def _start_button_style():
        return ""

    @staticmethod
    def _stop_button_style():
        return "QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b91c1c,stop:1 #ef4444);color:white;font-size:14px;font-weight:800;}QPushButton#primary:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #991b1b,stop:1 #dc2626);}"

    @staticmethod
    def _error_status_style():
        return "color:#7f1d1d;background:#fee2e2;border:1px solid #fecaca;"

    @staticmethod
    def _recording_status_style():
        return "color:#7f1d1d;background:#fff1f2;border:1px solid #fecdd3;"

    @staticmethod
    def _rendering_status_style():
        return "color:#1d4ed8;background:#dbeafe;border:1px solid #bfdbfe;"

    @staticmethod
    def _success_status_style():
        return "color:#166534;background:#dcfce7;border:1px solid #bbf7d0;"
