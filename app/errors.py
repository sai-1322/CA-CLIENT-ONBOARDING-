class ActionError(Exception):
    """A staff action that is refused on purpose (wrong state, missing approval, bad input).

    The API turns this into a clear JSON message and an HTTP 4xx status. It is never a crash.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
