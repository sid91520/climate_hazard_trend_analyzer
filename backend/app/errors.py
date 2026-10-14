"""One exception type for every "expected" failure, so main.py can turn all of them
into the same JSON shape:  {"error": {"code": ..., "message": ...}}
"""


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
