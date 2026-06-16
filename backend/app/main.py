"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.dependencies import register_exception_handlers, set_monitor, set_recorder, set_ros2_command
from app.features.analysis.router import router as analysis_router
from app.features.config.router import router as config_router
from app.features.jobs.router import router as jobs_router
from app.features.jobs.service import JobQueue, set_job_queue
from app.features.lerobot_export.router import router as lerobot_export_router
from app.features.media.router import router as media_router
from app.features.recording import ROS2BagRecorder
from app.features.recording.router import router as recording_router
from app.features.recordings.router import router as recordings_router
from app.features.topics.router import router as topics_router
from app.features.upload.router import router as upload_router
from app.features.validation import load_custom_validators
from app.features.validation.router import router as validation_router
from app.infra.ros2 import ROS2Command
from app.infra.ros2.thread import TopicMonitorThread
from app.settings import Settings, get_settings
from app.shared.log_manager import LogManager, set_log_manager

# Path to the built frontend files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Logging configuration (updated in lifespan based on settings.debug)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage the application lifecycle (startup/shutdown)."""
    recorder, monitor_thread = _initialize_services()

    # JobQueue requires an asyncio loop, so start it inside lifespan
    job_queue = JobQueue()
    set_job_queue(job_queue)
    await job_queue.start()

    yield

    await job_queue.shutdown()
    _shutdown_services(recorder, monitor_thread)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional settings override for tests.

    Returns:
        The configured FastAPI application.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="OpenLUTRA",
        description="ROS2 topic recorder for teleoperation robots (ROS2-standard topics)",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware for the frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    app.include_router(recording_router)
    app.include_router(recordings_router)
    app.include_router(topics_router)
    app.include_router(config_router)
    app.include_router(analysis_router)
    app.include_router(media_router)
    app.include_router(jobs_router)
    app.include_router(validation_router)
    app.include_router(lerobot_export_router)
    app.include_router(upload_router)

    # Serve the built frontend (production mode)
    if FRONTEND_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}", operation_id="serveFrontend")
        async def serve_frontend(full_path: str) -> FileResponse:
            """Serve the frontend SPA for non-API routes."""
            file_path = FRONTEND_DIR / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


# Application instance for uvicorn
app = create_app()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _initialize_services() -> tuple[ROS2BagRecorder, TopicMonitorThread]:
    """Initialize all services and register them in the DI container."""
    settings = get_settings()
    _configure_log_level(settings)
    logger.info("Starting OpenLUTRA")
    logger.info("Output directory: %s", settings.output_dir)
    logger.info("Default topics: %s", settings.default_topics)

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    log_manager = LogManager(max_entries=settings.max_log_entries)
    set_log_manager(log_manager)

    ros2 = ROS2Command()
    set_ros2_command(ros2)

    recorder = ROS2BagRecorder(settings, ros2)
    set_recorder(recorder)

    monitor_thread = TopicMonitorThread(settings, log_manager)
    set_monitor(monitor_thread.start())

    # Load custom validators (failures do not abort startup).
    load_custom_validators()

    logger.info("All services initialized successfully")
    return recorder, monitor_thread


def _shutdown_services(recorder: ROS2BagRecorder, monitor_thread: TopicMonitorThread) -> None:
    """Clean up all services."""
    if recorder.is_recording:
        logger.warning("Recording is in progress during shutdown, stopping...")
        recorder.stop()

    monitor_thread.stop()
    logger.info("Application shutdown complete")


def _configure_log_level(settings: Settings) -> None:
    """Set log level to DEBUG when not running in production."""
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.getLogger().setLevel(level)
    logger.info("Log level: %s", logging.getLevelName(level))
