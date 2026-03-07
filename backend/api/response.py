from fastapi import HTTPException
from fastapi.responses import JSONResponse


def api_success(data: dict | list = None, message: str = "Success", status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status_code": status_code,
            "status": "success",
            "message": message,
            "data": data if data is not None else {},
        },
    )


def api_error(message: str, status_code: int = 400, error: dict | str = None) -> HTTPException:
    # We raise this directly so FastAPI handles it as an HTTP exception,
    # but we override the detail to match our schema.
    raise HTTPException(
        status_code=status_code,
        detail={
            "status_code": status_code,
            "status": "error",
            "message": message,
            "error": error if error is not None else {},
        },
    )
