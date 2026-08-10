"""Application-wide exception handlers."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.features.recording import AlreadyRecordingError, NotRecordingError, RecorderError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""

    @app.exception_handler(AlreadyRecordingError)
    async def _already_recording(_request: Request, exc: AlreadyRecordingError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(NotRecordingError)
    async def _not_recording(_request: Request, exc: NotRecordingError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(RecorderError)
    async def _recorder_error(_request: Request, exc: RecorderError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all so unexpected exceptions reach the UI toast with at least
        # the exception type instead of a bare "Internal Server Error".
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Unexpected server error ({detail}) — check the backend logs for details."},
        )
