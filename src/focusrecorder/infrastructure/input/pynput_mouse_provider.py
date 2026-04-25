from ...domain.ports.mouse_provider import MouseProvider


class PynputMouseProvider(MouseProvider):
    def __init__(self):
        from pynput import mouse as pynput_mouse

        self._mouse_module = pynput_mouse
        self._controller = pynput_mouse.Controller()
        self._listener = None

    def get_position(self) -> tuple[int, int]:
        x, y = self._controller.position
        return int(x), int(y)

    def start_listener(self, on_click):
        self._listener = self._mouse_module.Listener(on_click=on_click)
        self._listener.start()

    def stop_listener(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
