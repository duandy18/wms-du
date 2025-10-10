# app/api/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse


class BizError(Exception):
    code = "BIZ_ERROR"
    status = 400

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(message)
        if code:
            self.code = code
        if status:
            self.status = status
        self.message = message


class NotFoundError(BizError):
    def __init__(self, message: str):
        super().__init__(message, code="NOT_FOUND", status=404)


def biz_error_handler(_: Request, exc: BizError):
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
