from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.exceptions import LexAIError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LexAIError)
    async def lexai_error_handler(request: Request, exc: LexAIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Beklenmeyen bir hata oluştu"}},
        )
