"""Runs the repo's make targets in the background, one job at a time, and keeps their output."""

import itertools
import os
import re
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
# AWS IoT thing and thing group names.
NAME_PATTERN = re.compile(r"[A-Za-z0-9:_-]{1,128}")


@dataclass
class Step:
    label: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        # CONFIGURATION carries a whole recording config; show its size instead of the YAML.
        env = [f"{k}={v}" if len(v) <= 200 else f"{k}=<{len(v)} chars>" for k, v in self.env.items()]
        return shlex.join(env + self.args)


@dataclass
class Job:
    id: int
    title: str
    steps: list[Step]
    groups: list[str] = field(default_factory=list)
    bundle: str | None = None
    started: datetime = field(default_factory=datetime.now)
    status: str = "running"
    current: int = 0
    logs: list[list[str]] = field(default_factory=list)

    def step_status(self, index: int) -> str:
        if index < self.current:
            return "succeeded"
        if index == self.current:
            return self.status
        return "pending"


class JobRunning(Exception):
    def __init__(self, job: Job):
        super().__init__(f"Job #{job.id} ({job.title}) is running. Try again after it finishes.")
        self.job = job


_jobs: dict[int, Job] = {}
_ids = itertools.count(1)
_lock = threading.Lock()


def running() -> Job | None:
    return next((job for job in _jobs.values() if job.status == "running"), None)


def get(job_id: int) -> Job | None:
    return _jobs.get(job_id)


def recent(limit: int = 10) -> list[Job]:
    return sorted(_jobs.values(), key=lambda job: job.id, reverse=True)[:limit]


def start(title: str, steps: list[Step], groups: list[str] | None = None, bundle: str | None = None) -> Job:
    with _lock:
        if current := running():
            raise JobRunning(current)
        job = Job(next(_ids), title, steps, groups or [], bundle, logs=[[] for _ in steps])
        _jobs[job.id] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def _run(job: Job) -> None:
    for index, step in enumerate(job.steps):
        job.current = index
        log = job.logs[index]
        log.append(f"$ {step}")
        try:
            process = subprocess.Popen(
                step.args,
                cwd=EXAMPLE_ROOT,
                env={**os.environ, **step.env},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            log.append(str(e))
            job.status = "failed"
            return
        assert process.stdout is not None
        for line in process.stdout:
            log.append(line.rstrip("\n"))
        if process.wait() != 0:
            log.append(f"Failed with exit code {process.returncode}")
            job.status = "failed"
            return
    job.current = len(job.steps)
    job.status = "succeeded"


def push() -> list[Step]:
    return [Step("Build the image and push it to ECR", ["make", "push"])]


def release(version: str) -> list[Step]:
    return [Step(f"Create component {version}", ["make", "release", f"COMPONENT_VERSION={version}"])]


def deploy(group: str, version: str, configuration: str | None) -> list[Step]:
    env = {"THING_GROUP": group}
    if configuration:
        env["CONFIGURATION"] = configuration
    return [Step(f"Deploy {version} to {group}", ["make", "deploy", f"COMPONENT_VERSION={version}"], env)]


def create_group(group: str) -> list[Step]:
    return [Step(f"Create Thing Group {group}", ["aws", "iot", "create-thing-group", "--thing-group-name", group])]


def provision(thing: str, group: str) -> list[Step]:
    return [Step(f"Register {thing} in {group}", ["make", "provision", f"THING_NAME={thing}"], {"THING_GROUP": group})]


def image_tag() -> str:
    """The IMAGE_TAG `make push` / `make release` use."""
    return _image_source()[0]


def image_commit() -> str:
    """The commit IMAGE_TAG comes from, as "<hash> <subject>"."""
    return _image_source()[1]


def _image_source() -> list[str]:
    return subprocess.run(
        ["make", "-s", "image-tag"],
        cwd=EXAMPLE_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


CONFIG_ROOT = EXAMPLE_ROOT / "greengrass" / "config"


def recording_config_files() -> list[str]:
    return sorted(p.name for p in CONFIG_ROOT.glob("*.yaml"))


def recording_config(name: str) -> str:
    """Content of a recording config in greengrass/config/, sent with a deployment instead of a release."""
    if name not in recording_config_files():
        raise FileNotFoundError(name)
    return (CONFIG_ROOT / name).read_text()


def save_recording_config(name: str, content: str) -> None:
    if name not in recording_config_files():
        raise FileNotFoundError(name)
    (CONFIG_ROOT / name).write_text(content)
