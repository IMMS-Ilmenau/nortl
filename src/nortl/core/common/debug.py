import inspect


class DebugEntity:
    def __init__(self) -> None:
        self.debug_stack = inspect.trace()
