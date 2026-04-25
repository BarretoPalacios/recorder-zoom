from ...domain.ports.mouse_provider import MouseProvider


class NullMouseProvider(MouseProvider):
    def get_position(self) -> tuple[int, int]:
        return 0, 0

    def start_listener(self, on_click) -> None:
        return None

    def stop_listener(self) -> None:
        return None
