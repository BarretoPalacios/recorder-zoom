import wave
import platform

import numpy as np

HAS_AUDIO = False
try:
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    pass


SYSTEM_AUDIO_MODE = "system"
MIC_AUDIO_MODE = "mic"
BOTH_AUDIO_MODE = "both"


def list_microphone_devices() -> list[tuple[str, int | None]]:
    devices = [("Dispositivo por defecto", None)]
    if not HAS_AUDIO:
        return devices
    try:
        for index, device in enumerate(sd.query_devices()):
            if device["max_input_channels"] > 0:
                devices.append((device["name"], index))
    except Exception:
        pass
    return devices


def list_system_audio_devices() -> list[tuple[str, int]]:
    if not HAS_AUDIO:
        return []
    devices = []
    try:
        for index, device in enumerate(sd.query_devices()):
            name = str(device.get("name", "")).lower()
            if device["max_input_channels"] > 0 and _is_system_capture_device(name):
                devices.append((device["name"], index))
    except Exception:
        return []
    return devices


class SounddeviceAudioRecorder:
    SAMPLERATE = 44100

    def __init__(self, device=None, mode: str = MIC_AUDIO_MODE):
        self.device = device
        self.mode = mode
        self._frames = []
        self._level = 0
        self._stream = None
        self._is_paused = False
        self._channels = 1
        self._samplerate = self.SAMPLERATE

    @property
    def level(self) -> int:
        return self._level

    def start(self):
        if not HAS_AUDIO:
            return
        self._frames = []
        self._is_paused = False
        stream_kwargs = self._build_stream_kwargs()
        self._stream = sd.InputStream(
            dtype="float32",
            callback=self._callback,
            **stream_kwargs,
        )
        self._stream.start()

    def stop(self, output_path: str) -> str | None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._is_paused = False

        audio_data = self._collect_audio_data()
        if audio_data is None:
            return None
        if not output_path:
            return None

        with wave.open(output_path, "w") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(int(self._samplerate))
            wf.writeframes(_float_to_pcm16(audio_data).tobytes())

        return output_path

    def pause(self) -> None:
        self._is_paused = True
        self._level = 0

    def resume(self) -> None:
        self._is_paused = False

    def _callback(self, indata, frames, time, status):
        if self._is_paused:
            self._level = 0
            return
        self._frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        self._level = min(int(rms * 300), 100)

    def _build_stream_kwargs(self) -> dict:
        if self.mode == SYSTEM_AUDIO_MODE:
            return self._build_system_stream_kwargs()
        self._channels = 1
        self._samplerate = self.SAMPLERATE
        return {
            "device": self.device,
            "samplerate": self._samplerate,
            "channels": self._channels,
        }

    def _build_system_stream_kwargs(self) -> dict:
        if platform.system() != "Windows":
            raise RuntimeError("El audio del escritorio solo esta disponible en Windows.")

        device_index = self.device
        if device_index is None:
            available = list_system_audio_devices()
            device_index = available[0][1] if available else None
        if device_index is None:
            raise RuntimeError("No se encontro un dispositivo compatible para capturar el audio del escritorio.")

        device_info = sd.query_devices(device_index)
        input_channels = int(device_info.get("max_input_channels", 0))
        if input_channels <= 0:
            raise RuntimeError("El dispositivo seleccionado no permite capturar audio del sistema.")

        self._channels = min(max(input_channels, 1), 2)
        self._samplerate = int(device_info.get("default_samplerate", self.SAMPLERATE) or self.SAMPLERATE)
        return {
            "device": device_index,
            "samplerate": self._samplerate,
            "channels": self._channels,
        }

    def _collect_audio_data(self) -> np.ndarray | None:
        if not self._frames:
            return None
        return _postprocess_audio(np.concatenate(self._frames, axis=0))


class CombinedAudioRecorder:
    def __init__(self, mic_device=None, system_device=None):
        self.mic_recorder = SounddeviceAudioRecorder(device=mic_device, mode=MIC_AUDIO_MODE)
        self.system_recorder = SounddeviceAudioRecorder(device=system_device, mode=SYSTEM_AUDIO_MODE)

    @property
    def level(self) -> int:
        return max(self.mic_recorder.level, self.system_recorder.level)

    def start(self):
        self.system_recorder.start()
        self.mic_recorder.start()

    def pause(self):
        self.mic_recorder.pause()
        self.system_recorder.pause()

    def resume(self):
        self.mic_recorder.resume()
        self.system_recorder.resume()

    def stop(self, output_path: str) -> str | None:
        self.mic_recorder.stop("")
        self.system_recorder.stop("")
        mic_data = self.mic_recorder._collect_audio_data()
        system_data = self.system_recorder._collect_audio_data()
        mixed = _mix_audio_arrays(
            mic_data,
            int(self.mic_recorder._samplerate),
            int(self.mic_recorder._channels),
            system_data,
            int(self.system_recorder._samplerate),
            int(self.system_recorder._channels),
        )
        if mixed is None:
            return None
        with wave.open(output_path, "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(_float_to_pcm16(_postprocess_audio(mixed)).tobytes())
        return output_path


def _mix_audio_arrays(
    mic_data: np.ndarray | None,
    mic_rate: int,
    mic_channels: int,
    system_data: np.ndarray | None,
    system_rate: int,
    system_channels: int,
) -> np.ndarray | None:
    if mic_data is None and system_data is None:
        return None
    target_rate = 48000
    target_channels = 2
    prepared = []
    if mic_data is not None:
        prepared.append(_prepare_audio(mic_data, mic_rate, mic_channels, target_rate, target_channels))
    if system_data is not None:
        prepared.append(_prepare_audio(system_data, system_rate, system_channels, target_rate, target_channels))
    max_len = max(track.shape[0] for track in prepared)
    mixed = np.zeros((max_len, target_channels), dtype=np.float32)
    for track in prepared:
        mixed[: track.shape[0]] += track.astype(np.float32)
    mixed /= max(len(prepared), 1)
    return np.clip(mixed, -1.0, 1.0).astype(np.float32)


def _prepare_audio(data: np.ndarray, source_rate: int, source_channels: int, target_rate: int, target_channels: int) -> np.ndarray:
    audio = data
    if audio.ndim == 1:
        audio = audio[:, None]
    if source_channels == 1 and target_channels == 2:
        audio = np.repeat(audio, 2, axis=1)
    elif source_channels > target_channels:
        audio = audio[:, :target_channels]
    elif source_channels < target_channels:
        audio = np.pad(audio, ((0, 0), (0, target_channels - source_channels)), mode="edge")
    if source_rate == target_rate:
        return audio.astype(np.float32)
    duration = audio.shape[0] / max(source_rate, 1)
    target_len = max(int(duration * target_rate), 1)
    src_x = np.linspace(0, audio.shape[0] - 1, num=audio.shape[0], dtype=np.float32)
    dst_x = np.linspace(0, audio.shape[0] - 1, num=target_len, dtype=np.float32)
    resampled = np.zeros((target_len, target_channels), dtype=np.float32)
    for channel in range(target_channels):
        resampled[:, channel] = np.interp(dst_x, src_x, audio[:, channel].astype(np.float32))
    return resampled.astype(np.float32)


def _postprocess_audio(audio: np.ndarray) -> np.ndarray:
    processed = audio.astype(np.float32, copy=True)
    if processed.ndim == 1:
        processed = processed[:, None]

    processed -= processed.mean(axis=0, keepdims=True)

    # Repara picos impulsivos que suelen sonar como "tik tik".
    if processed.shape[0] >= 3:
        prev = processed[:-2]
        curr = processed[1:-1]
        nxt = processed[2:]
        neighbor_mean = (prev + nxt) * 0.5
        spike_strength = np.abs(curr - neighbor_mean)
        threshold = np.maximum(0.18, np.std(processed, axis=0, keepdims=True) * 5.5)
        spike_mask = spike_strength > threshold
        curr[spike_mask] = neighbor_mean[spike_mask]

    # Suavizado muy corto para limpiar grano sin volver opaca la voz.
    if processed.shape[0] >= 5:
        kernel = np.array([0.06, 0.24, 0.40, 0.24, 0.06], dtype=np.float32)
        smoothed = np.zeros_like(processed)
        for channel in range(processed.shape[1]):
            smoothed[:, channel] = np.convolve(processed[:, channel], kernel, mode="same")
        processed = processed * 0.7 + smoothed * 0.3

    # Limiter suave para evitar saturación áspera.
    processed = np.tanh(processed * 1.15) / np.tanh(1.15)
    return np.clip(processed, -1.0, 1.0).astype(np.float32)


def _is_system_capture_device(name: str) -> bool:
    lowered = name.lower()
    if platform.system() == "Windows":
        return "mezcla" in lowered or "stereo mix" in lowered or "what u hear" in lowered
    if platform.system() == "Linux":
        return "monitor" in lowered
    return False


def _float_to_pcm16(audio: np.ndarray) -> np.ndarray:
    clipped = np.clip(audio.astype(np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)
