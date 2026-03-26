class ServiceError(Exception):
    def __init__(self, code: int, msg: str, cause: Exception | None = None) -> None:
        self.code = code
        self.msg = msg
        self.cause = cause
        super().__init__(msg)
