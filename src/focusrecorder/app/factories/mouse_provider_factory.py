from ...domain.ports.mouse_provider import MouseProvider


def create_mouse_provider() -> MouseProvider:
    try:
        from ...infrastructure.input.pynput_mouse_provider import PynputMouseProvider

        return PynputMouseProvider()
    except Exception:
        from ...infrastructure.input.null_mouse_provider import NullMouseProvider

        return NullMouseProvider()
