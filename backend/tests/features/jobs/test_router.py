"""Tests for the jobs router glue (list endpoint)."""

from app.features.jobs import service as jobs_service
from app.features.jobs.router import list_jobs
from app.features.jobs.service import JobQueue


async def test_list_jobs_returns_snapshot() -> None:
    previous = jobs_service._job_queue
    jobs_service.set_job_queue(JobQueue())
    try:
        response = await list_jobs()
        assert response.jobs == []
    finally:
        jobs_service._job_queue = previous
