# Focus Recorder Studio - README v2

Versión de documentación actualizada para reflejar los cambios reales aplicados al proyecto hasta ahora.

## Resumen

El proyecto evolucionó desde una interfaz anterior más básica hacia una experiencia más moderna enfocada en:

- grabación para tutoriales y contenido vertical
- seguimiento de foco alrededor del cursor
- exportación horizontal, vertical o doble
- controles más claros dentro de la ventana
- mejoras progresivas en captura, render, audio y persistencia

La aplicación actual arranca con una interfaz `PyQt6` y mantiene un motor de captura/render propio sobre `mss`, `OpenCV` y `FFmpeg`.

## Cambios principales realizados

### 1. Interfaz renovada

Se rehizo la interfaz principal para que se sienta más actual, limpia y orientada a grabación.

Cambios aplicados:

- consolidación de la ventana principal en `PyQt6`
- panel visual tipo studio con mejor jerarquía
- bloques separados para destino, formato, preview, audio, estado y acciones
- botones funcionales para:
  - `Abrir carpeta`
  - `Mostrar último`
  - `Reproducir`
- preview más pequeño y con opción para desactivarlo
- selector de formato:
  - `Pantalla`
  - `TikTok`
  - `Ambos`
- selector de calidad:
  - `Baja`
  - `Media`
  - `Alta`
  - `Muy alta`

Archivos clave:

- [src/focusrecorder/main.py](recorder-zoom-v2.0-main/src/focusrecorder/main.py)
- [src/focusrecorder/presentation/qt/studio_window.py](recorder-zoom-v2.0-main/src/focusrecorder/presentation/qt/studio_window.py)

### 2. Persistencia de configuración

La app ahora recuerda entre sesiones:

- zoom
- suavidad
- FPS
- carpeta de salida
- modo de exportación
- preview activado o desactivado
- audio activado y modo de audio
- hotkeys
- calidad seleccionada

Archivos clave:

- [src/focusrecorder/config/settings.py](recorder-zoom-v2.0-main/src/focusrecorder/config/settings.py)
- [src/focusrecorder/config/config.py](recorder-zoom-v2.0-main/src/focusrecorder/config/config.py)
- [src/focusrecorder/config/preferences.py](recorder-zoom-v2.0-main/src/focusrecorder/config/preferences.py)

### 3. Hotkeys editables

Las teclas de pausa y stop dejaron de ser fijas.

Ahora:

- se pueden editar desde la UI
- el flujo es tipo “haz click y presiona una tecla”
- soporta `F2` a `F12`
- evita conflictos entre ambas teclas
- se guardan automáticamente

Hotkeys por defecto:

- `F7`: pausa o reanuda
- `F10`: detener y procesar

### 4. Comportamiento de grabación

Cambios funcionales incorporados:

- al iniciar la grabación, la ventana se minimiza
- `F7` pausa o reanuda
- `F10` termina la grabación y lanza el render
- nombres automáticos únicos si el usuario no escribe nombre
- soporte para abrir la carpeta y ubicar el último video generado

Archivo clave:

- [src/focusrecorder/recorder.py](recorder-zoom-v2.0-main/src/focusrecorder/recorder.py)

## Motor de captura y render

### Backend de captura actual

La app usa una fábrica de backends:

- `DXcam` si está disponible en Windows
- `MSS` como fallback

En el estado actual del entorno de trabajo analizado, se verificó que la app está cayendo en:

- `MssCaptureBackend`

Archivos:

- [src/focusrecorder/app/factories/capture_backend_factory.py](recorder-zoom-v2.0-main/src/focusrecorder/app/factories/capture_backend_factory.py)
- [src/focusrecorder/infrastructure/capture/mss_backend.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/capture/mss_backend.py)
- [src/focusrecorder/infrastructure/capture/dxcam_backend.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/capture/dxcam_backend.py)

### Seguimiento de foco

El sistema de seguimiento fue ajustado varias veces para verse más natural.

Cambios relevantes:

- interpolación entre muestras de mouse
- suavizado del follow por tiempo
- reducción de zonas muertas rígidas
- límites de corrección para evitar saltos bruscos

Archivo:

- [src/focusrecorder/infrastructure/rendering/adaptive_renderer.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/rendering/adaptive_renderer.py)

### Cursor en video

Se probaron varias estrategias.

Evolución:

1. cursor artificial simple
2. intento de cursor nativo de Windows
3. fallback más estable basado en coordenadas del mouse
4. halo visual y suavizado del movimiento del cursor

Estado actual:

- el cursor se dibuja como overlay visual ligero
- tiene halo
- resalta más al hacer click
- se suavizó para que no se vea tan tosco

Archivo:

- [src/focusrecorder/infrastructure/capture/windows_cursor.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/capture/windows_cursor.py)

### Escritura temporal y rendimiento

Para reducir tirones durante captura:

- se cambió el orden de codecs temporales
- se priorizaron opciones más rápidas
- se agregó escritura temporal asíncrona con cola
- se amplió el buffer de escritura
- se privilegia continuidad de captura frente a bloquear el hilo principal

Archivo:

- [src/focusrecorder/recorder.py](recorder-zoom-v2.0-main/src/focusrecorder/recorder.py)

### Codificación final y calidad

El render final ahora intenta usar aceleración por hardware cuando existe.

Orden de preferencia:

- `h264_nvenc`
- `h264_qsv`
- `h264_amf`
- `libx264`

Además, la calidad elegida desde la UI ahora sí afecta la codificación final.

Mapeo actual:

- `Baja`
- `Media`
- `Alta`
- `Muy alta`

Archivos:

- [src/focusrecorder/infrastructure/encoding/h264_encoder.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/encoding/h264_encoder.py)
- [src/focusrecorder/infrastructure/rendering/adaptive_renderer.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/rendering/adaptive_renderer.py)

## Audio

### Modos de audio implementados

La app soporta:

- `Microfono`
- `Escritorio`
- `Ambos`

En Windows, el audio de escritorio se apoya en dispositivos compatibles detectables, como:

- `Mezcla estéreo`

### Mejoras aplicadas al audio

Se hicieron varios ajustes para reducir ruido y artefactos:

- captura interna en `float32`
- mezcla y remuestreo a formato consistente
- postproceso ligero antes de guardar
- reparación de picos impulsivos
- suavizado corto
- limitador suave

Objetivo:

- reducir chasquidos del tipo `tik tik tik`
- limpiar un poco más la voz o audio del sistema

Archivo:

- [src/focusrecorder/infrastructure/audio/sounddevice_audio.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/audio/sounddevice_audio.py)

## Funciones de usuario ya disponibles

- elegir carpeta de salida
- poner nombre manual al archivo
- generar nombre automático si no se escribe uno
- grabar en pantalla, TikTok o ambos
- elegir calidad
- activar o desactivar preview
- elegir audio:
  - micrófono
  - escritorio
  - ambos
- abrir carpeta
- mostrar último
- reproducir último
- editar hotkeys

## Flujo actual recomendado

1. Abrir la app con `python -m focusrecorder`
2. Elegir formato
3. Elegir calidad
4. Ajustar zoom, suavidad y FPS
5. Definir audio si hace falta
6. Configurar hotkeys si quieres
7. Iniciar grabación
8. Detener con la hotkey o desde el botón

## Estado actual del proyecto

### Mejoras

- interfaz mucho más moderna que la original
- mejor organización visual
- más control desde UI
- hotkeys persistentes
- cursor visual más usable
- seguimiento más natural que las primeras versiones
- motor más estable que antes
- opción de calidad ya conectada
- audio mejorado

### Limitaciones conocidas

Todavía pueden aparecer limitaciones en estos casos:

- videos muy pesados reproduciéndose de fondo
- escenas con mucho movimiento continuo
- variación de fluidez según el backend disponible
- en Windows, `MSS` sigue teniendo límites frente a soluciones más fuertes como una captura más nativa o más cercana a OBS

## Archivos más importantes tocados en esta etapa

- [src/focusrecorder/main.py](recorder-zoom-v2.0-main/src/focusrecorder/main.py)
- [src/focusrecorder/recorder.py](recorder-zoom-v2.0-main/src/focusrecorder/recorder.py)
- [src/focusrecorder/presentation/qt/studio_window.py](recorder-zoom-v2.0-main/src/focusrecorder/presentation/qt/studio_window.py)
- [src/focusrecorder/presentation/qt/recording_presenter.py](recorder-zoom-v2.0-main/src/focusrecorder/presentation/qt/recording_presenter.py)
- [src/focusrecorder/infrastructure/rendering/adaptive_renderer.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/rendering/adaptive_renderer.py)
- [src/focusrecorder/infrastructure/encoding/h264_encoder.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/encoding/h264_encoder.py)
- [src/focusrecorder/infrastructure/audio/sounddevice_audio.py](Drecorder-zoom-v2.0-main/src/focusrecorder/infrastructure/audio/sounddevice_audio.py)
- [src/focusrecorder/infrastructure/capture/mss_backend.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/capture/mss_backend.py)
- [src/focusrecorder/infrastructure/capture/windows_cursor.py](recorder-zoom-v2.0-main/src/focusrecorder/infrastructure/capture/windows_cursor.py)
- [src/focusrecorder/config/settings.py](recorder-zoom-v2.0-main/src/focusrecorder/config/settings.py)
- [src/focusrecorder/config/config.py](recorder-zoom-v2.0-main/src/focusrecorder/config/config.py)
- [src/focusrecorder/config/preferences.py](recorder-zoom-v2.0-main/src/focusrecorder/config/preferences.py)

## Comando de arranque

```powershell
python -m focusrecorder
```

## Nota final

Este `README` documenta el estado actual del proyecto después de una serie larga de correcciones, rediseño de UI y mejoras incrementales del motor.
