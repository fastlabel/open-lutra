"""Local web console: watch thing groups and devices, release and deploy the component."""

import difflib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

import yaml
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import aws, bundles, jobs
from app.octicons import octicon

app = FastAPI(title="OpenLUTRA Greengrass console")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _format_time(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S") if value else "-"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _ago(value: datetime | None) -> str:
    if value is None:
        return "-"
    seconds = (datetime.now().astimezone() - value.astimezone()).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{_count(int(seconds // 3600), 'hour')} ago"
    return f"{_count(int(seconds // 86400), 'day')} ago"


templates.env.filters["time"] = _format_time
templates.env.filters["ago"] = _ago
templates.env.globals["running_job"] = jobs.running
templates.env.globals["component_name"] = aws.COMPONENT_NAME
templates.env.globals["conditions"] = aws.CONDITIONS
templates.env.globals["disk_free_warning"] = aws.DISK_FREE_WARNING_PERCENT
templates.env.globals["disk_days_warning"] = aws.DISK_DAYS_WARNING
templates.env.globals["problems"] = aws.PROBLEMS
templates.env.globals["octicon"] = octicon
templates.env.globals["bundle"] = bundles.get
templates.env.globals["secrets_on_disk"] = bundles.with_secret


def _render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def _error(request: Request, message: str, status_code: int = 400, **context) -> HTMLResponse:
    return _render(request, "error.html", status_code, message=message, **context)


@app.exception_handler(ClientError)
@app.exception_handler(BotoCoreError)
async def _aws_error(request: Request, exc: Exception) -> HTMLResponse:
    return _error(request, f"AWS call failed: {exc}", 502, hint=True)


@app.exception_handler(jobs.JobRunning)
async def _job_running(request: Request, exc: jobs.JobRunning) -> HTMLResponse:
    return _error(request, str(exc), 409, job=exc.job)


def _configuration(recording_config_file: str, content: str | None = None) -> str:
    """Deployment configuration that carries the recording config itself, so a new config needs no new version."""
    if content is None:
        content = jobs.recording_config(recording_config_file)
    return json.dumps({"RecordingConfigFile": recording_config_file, "RecordingConfig": content}, ensure_ascii=False)


def _yaml_error(content: str) -> str | None:
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return str(e)
    return None if isinstance(parsed, dict) else "The top level is not a key-value mapping"


def _editor(name: str | None, current: aws.Deployment | None = None) -> dict:
    """Config picked for an editor, and its starting content: what the current deployment sent if it is the
    same config, else the file in greengrass/config/."""
    files = jobs.recording_config_files()
    if name not in files:
        name = files[0] if files else None
    if name is None:
        return {"config_name": None, "config_content": "", "config_source": ""}
    if current and current.recording_config_file == name and current.recording_config is not None:
        return {"config_name": name, "config_content": current.recording_config, "config_source": "Currently deployed"}
    return {"config_name": name, "config_content": jobs.recording_config(name), "config_source": "From file"}


@app.get("/configs/content")
def config_content(name: str) -> PlainTextResponse:
    try:
        return PlainTextResponse(jobs.recording_config(name))
    except FileNotFoundError:
        raise HTTPException(404, "config not found") from None


def _config_diff(current: aws.Deployment | None, configuration: str | None) -> list[str] | None:
    """Changed lines between the current deployment's recording config and the new one; None if either is unknown."""
    before = json.loads(current.configuration).get("RecordingConfig") if current and current.configuration else None
    after = json.loads(configuration).get("RecordingConfig") if configuration else None
    if before is None or after is None:
        return None
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), "current", "after deploy", lineterm="", n=1)
    return list(lines)[2:]


def _released_version(tag: str, versions: list[str]) -> str | None:
    """The newest component version built from the given image tag."""
    return next((v for v in versions if aws.image_tag(v) == tag), None)


# --- Dashboard ---


def _groups_context() -> dict:
    groups = aws.groups()
    totals = dict.fromkeys(aws.CONDITIONS, 0)
    for group in groups:
        for key, count in group.counts().items():
            totals[key] += count
    return {
        "groups": groups,
        "totals": totals,
        "device_total": sum(totals.values()),
        "versions_running": aws.version_distribution(groups),
    }


@app.get("/")
def dashboard(request: Request, period: str = "today") -> HTMLResponse:
    tag = jobs.image_tag()
    versions = aws.component_versions()
    context = _groups_context()
    groups = context["groups"]
    released = _released_version(tag, versions)
    return _render(
        request,
        "dashboard.html",
        **context,
        image_tag=tag,
        commit=jobs.image_commit(),
        images_exist=aws.images_exist(tag),
        latest_version=versions[0] if versions else None,
        released_version=released,
        next_version=aws.next_version(versions),
        deployed_groups=[g.name for g in groups if released and g.deployment and g.deployment.version == released],
        group_names=[g.name for g in groups],
        config_files=jobs.recording_config_files(),
        **_editor(None),
        **_monitor_context(period, groups),
    )


def _health_checks(devices: list[aws.Device], expected: dict[str, str | None]) -> list[dict]:
    """Fleet-wide checks, problems first. Each lists the devices it concerns."""

    def check(name: str, level: str, bad: list[str], problem: str, fine: str) -> dict:
        names = ", ".join(bad[:3]) + (f" and {len(bad) - 3} more" if len(bad) > 3 else "")
        return {"name": name, "level": level if bad else "ok", "detail": f"{names}: {problem}" if bad else fine}

    total = len(devices)
    checks = [
        check(
            "Connection",
            "error",
            [d.name for d in devices if "offline" in d.monitoring.problems],
            "no status received for over 10 minutes",
            f"Receiving status from all {_count(total, 'device')}",
        ),
        check(
            "Disk space",
            "warning",
            [d.name for d in devices if "disk" in d.monitoring.problems],
            f"under {aws.DISK_FREE_WARNING_PERCENT}% free or full within {aws.DISK_DAYS_WARNING} days",
            f"No device will be full within {aws.DISK_DAYS_WARNING} days",
        ),
        check(
            "Loss rate",
            "warning",
            [d.name for d in devices if (d.monitoring.max_loss_rate or 0) >= aws.LOSS_WARNING_PERCENT],
            f"loss rate above {aws.LOSS_WARNING_PERCENT}%",
            f"All devices under {aws.LOSS_WARNING_PERCENT}%",
        ),
        check(
            "Deployment",
            "warning",
            [
                d.name
                for d in devices
                if d.deployment_status in aws.IN_PROGRESS
                or {"deploy_failed", "version"} & set(d.issues(expected[d.name]))
            ],
            "not on the deployed version",
            "All devices run the deployed version",
        ),
        check(
            "OpenLUTRA",
            "error",
            [d.name for d in devices if d.monitoring.openlutra_up is False],
            "OpenLUTRA not responding",
            "Running on all responding devices",
        ),
    ]
    order = {"error": 0, "warning": 1, "ok": 2}
    return sorted(checks, key=lambda c: order[c["level"]])


def _monitor_context(period: str, groups: list[aws.GroupSummary] | None = None) -> dict:
    if period not in aws.PERIODS:
        period = "today"
    groups = aws.groups() if groups is None else groups
    devices = [d for g in groups for d in g.devices]
    group_of = {d.name: g.name for g in groups for d in g.devices}
    expected = {d.name: g.deployment.version if g.deployment else None for g in groups for d in g.devices}
    names = [d.name for d in devices]
    collected = aws.collection(names, period)
    checks = _health_checks(devices, expected)
    peak = max((passed + other for _, passed, other in collected.buckets), default=0)
    step = 10 if peak > 20 else 2 if peak > 4 else 0.5
    return {
        "period": period,
        "periods": aws.PERIODS,
        "collected": collected,
        "axis_max": max(step, -(-peak // step) * step),
        "devices": devices,
        "group_of": group_of,
        "checks": checks,
        "online": sum(1 for d in devices if "offline" not in d.monitoring.problems),
        "recording": sum(1 for d in devices if d.monitoring.recording),
        "issues": sum(1 for c in checks if c["level"] != "ok"),
    }


@app.get("/dashboard/monitor")
def dashboard_monitor(request: Request, period: str = "today") -> HTMLResponse:
    return _render(request, "_monitor.html", **_monitor_context(period))


@app.get("/dashboard/groups")
def dashboard_groups(request: Request) -> HTMLResponse:
    return _render(request, "_dashboard_groups.html", **_groups_context())


# --- Thing groups ---


def _valid_name(name: str) -> bool:
    return jobs.NAME_PATTERN.fullmatch(name) is not None


@app.get("/groups/new")
def new_group_page(request: Request) -> HTMLResponse:
    return _render(request, "new_group.html")


@app.post("/groups")
def create_group(request: Request, name: Annotated[str, Form()]) -> Response:
    if not _valid_name(name):
        return _error(request, "Thing Group names may contain only letters, digits, and : _ - (up to 128 characters).")
    if name in aws.thing_groups():
        return _error(request, f"Thing Group {name} already exists.")
    job = jobs.start(f"Create Thing Group {name}", jobs.create_group(name), [name])
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


def _current(group: str) -> aws.Deployment | None:
    history = aws.deployments(group)
    return history[0] if history else None


@app.get("/groups/{group}")
def group_overview(request: Request, group: str) -> HTMLResponse:
    current = _current(group)
    return _render(
        request,
        "group.html",
        tab="overview",
        group=group,
        current=current,
        current_tag=aws.image_tag(current.version) if current else None,
    )


@app.get("/groups/{group}/devices")
def group_devices(request: Request, group: str, expected: str | None = None) -> HTMLResponse:
    devices = aws.devices(group)
    counts = dict.fromkeys(aws.CONDITIONS, 0)
    for device in devices:
        counts[device.condition(expected)] += 1
    return _render(request, "_devices.html", group=group, devices=devices, expected=expected, counts=counts)


@app.get("/groups/{group}/register")
def register_page(request: Request, group: str) -> HTMLResponse:
    return _render(request, "register.html", tab="overview", group=group, bundles=bundles.with_secret())


@app.post("/groups/{group}/register")
def register_device(request: Request, group: str, thing: Annotated[str, Form()]) -> Response:
    if not _valid_name(thing):
        return _error(request, "Device names may contain only letters, digits, and : _ - (up to 128 characters).")
    job = jobs.start(f"Register {thing}", jobs.provision(thing, group), [group], thing)
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


def _bundle_with_secret(thing: str) -> str:
    bundle = bundles.get(thing) if _valid_name(thing) else None
    if bundle is None or not bundle.has_secret:
        raise HTTPException(404, "bundle not found")
    return thing


@app.get("/secrets")
def secrets_page(request: Request) -> HTMLResponse:
    return _render(request, "secrets.html", bundles=bundles.all_bundles())


@app.get("/bundles/{thing}.zip")
def download_bundle(thing: str) -> Response:
    name = _bundle_with_secret(thing)
    return Response(
        bundles.download(name),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@app.post("/bundles/{thing}/delete")
def delete_bundle(thing: str, back: Annotated[str, Form()] = "/") -> Response:
    bundles.delete_secret(_bundle_with_secret(thing))
    return RedirectResponse(back if back.startswith("/") else "/", status_code=303)


@app.get("/groups/{group}/devices/{name}")
def device_page(request: Request, group: str, name: str) -> HTMLResponse:
    return _render(request, "device.html", **_device_context(group, name))


@app.get("/groups/{group}/devices/{name}/body")
def device_body(request: Request, group: str, name: str) -> HTMLResponse:
    return _render(request, "_device_body.html", **_device_context(group, name))


def _device_context(group: str, name: str) -> dict:
    if not _valid_name(name):
        raise HTTPException(404, "device not found")
    current = _current(group)
    expected = current.version if current else None
    device = aws.device(name)
    return {
        "group": group,
        "device": device,
        "condition": device.condition(expected),
        "expected": expected,
        "detail": aws.device_detail(name),
    }


@app.get("/groups/{group}/history")
def group_history(request: Request, group: str) -> HTMLResponse:
    history = aws.deployments(group)
    return _render(
        request,
        "history.html",
        tab="history",
        group=group,
        history=history,
        image_tags={d.version: aws.image_tag(d.version) for d in history},
    )


@app.get("/groups/{group}/deploy")
def group_deploy(request: Request, group: str, version: str | None = None) -> HTMLResponse:
    current = _current(group)
    versions = aws.component_versions()
    return _render(
        request,
        "deploy.html",
        tab="deploy",
        group=group,
        current=current,
        versions=[(v, aws.image_tag(v)) for v in versions],
        selected=version or (current.version if current else None),
        config_files=jobs.recording_config_files(),
        **_editor(current.recording_config_file if current else None, current),
    )


# --- Release ---


@app.get("/release/all")
def release_all_page(request: Request) -> HTMLResponse:
    tag = jobs.image_tag()
    return _render(
        request,
        "release_all.html",
        image_tag=tag,
        commit=jobs.image_commit(),
        images_exist=aws.images_exist(tag),
        next_version=aws.next_version(aws.component_versions()),
        groups=aws.thing_groups(),
        config_files=jobs.recording_config_files(),
        **_editor(None),
    )


@app.get("/versions")
def versions_page(request: Request) -> HTMLResponse:
    in_use: dict[str, list[str]] = {}
    for group in aws.groups():
        if group.deployment:
            in_use.setdefault(group.deployment.version, []).append(group.name)
    return _render(
        request,
        "versions.html",
        versions=[(v, aws.image_tag(v)) for v in aws.component_versions()],
        in_use=in_use,
    )


# --- Confirm and run ---


@app.post("/confirm")
def confirm(
    request: Request,
    action: Annotated[str, Form()],
    version: Annotated[str, Form()],
    group: Annotated[list[str] | None, Form()] = None,
    recording_config_file: Annotated[str | None, Form()] = None,
    recording_config: Annotated[str | None, Form()] = None,
    save_config: Annotated[bool, Form()] = False,
    configuration: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    if action not in ("deploy", "pipeline"):
        raise HTTPException(400, f"unknown action: {action}")
    groups = list(dict.fromkeys(group or []))
    if not groups:
        return _error(request, "Select at least one Thing Group to deploy to.")
    if recording_config_file and recording_config_file not in jobs.recording_config_files():
        return _error(request, f"Recording config {recording_config_file} is not in greengrass/config/.")
    if recording_config_file:
        content = recording_config.replace("\r\n", "\n") if recording_config is not None else None
        if content is not None and (problem := _yaml_error(content)):
            return _error(request, f"Cannot parse the recording config as YAML: {problem}")
        configuration = _configuration(recording_config_file, content)
    if not configuration:
        return _error(request, "Select a recording config.")

    new_tag: str | None
    if action == "pipeline":
        new_tag = jobs.image_tag()
        if version in aws.component_versions():
            return _error(request, f"Version {version} already exists. Specify a different version.")
        steps = ([] if aws.images_exist(new_tag) else jobs.push()) + jobs.release(version)
    else:
        new_tag = aws.image_tag(version)
        steps = []
    for g in groups:
        steps += jobs.deploy(g, version, configuration)

    def target(name: str) -> dict:
        current = _current(name)
        diff = _config_diff(current, configuration)
        return {
            "group": name,
            "current": current,
            "current_tag": aws.image_tag(current.version) if current else None,
            "devices": aws.devices(name),
            "config_diff": diff,
            "config_changes": sum(1 for line in diff or [] if line[:1] in "+-"),
        }

    return _render(
        request,
        "confirm.html",
        action=action,
        groups=groups,
        version=version,
        configuration=configuration,
        new_config=json.loads(configuration).get("RecordingConfigFile") if configuration else None,
        new_tag=new_tag,
        targets=[target(g) for g in groups],
        steps=steps,
        save_config=save_config and bool(recording_config_file),
    )


@app.post("/jobs")
def start_job(
    request: Request,
    action: Annotated[str, Form()],
    version: Annotated[str | None, Form()] = None,
    group: Annotated[list[str] | None, Form()] = None,
    configuration: Annotated[str | None, Form()] = None,
    save_config: Annotated[bool, Form()] = False,
) -> Response:
    groups = list(dict.fromkeys(group or []))
    if action in ("deploy", "pipeline") and not groups:
        return _error(request, "Select at least one Thing Group to deploy to.")
    if action in ("deploy", "pipeline") and not configuration:
        return _error(request, "No recording config. Nothing was deployed.")
    if configuration:
        sent = json.loads(configuration)
        # The name becomes a file name on the device, so it must not reach outside the component's work folder.
        if not re.fullmatch(r"[A-Za-z0-9._-]+\.yaml", sent.get("RecordingConfigFile", "")):
            return _error(request, "Invalid recording config file name. Nothing was deployed.")
        if save_config:
            if sent["RecordingConfigFile"] not in jobs.recording_config_files():
                return _error(request, "Cannot save to a file outside greengrass/config/. Nothing was deployed.")
            jobs.save_recording_config(sent["RecordingConfigFile"], sent["RecordingConfig"])

    deploys = [step for g in groups for step in jobs.deploy(g, version or "", configuration)]
    targets = ", ".join(groups)
    if action == "push":
        job = jobs.start("Build and push the image", jobs.push())
    elif action == "release" and version:
        job = jobs.start(f"Create component {version}", jobs.release(version))
    elif action == "deploy" and version:
        job = jobs.start(f"Deploy {version} to {targets}", deploys, groups)
    elif action == "pipeline" and version:
        steps = [] if aws.images_exist(jobs.image_tag()) else jobs.push()
        job = jobs.start(f"Release {version} and deploy to {targets}", steps + jobs.release(version) + deploys, groups)
    else:
        raise HTTPException(400, f"invalid request for action {action}")
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


# --- Jobs ---


@app.get("/jobs")
def jobs_page(request: Request) -> HTMLResponse:
    return _render(request, "jobs.html", jobs=jobs.recent(50))


def _job(job_id: int) -> jobs.Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/jobs/{job_id}")
def job_page(request: Request, job_id: int) -> HTMLResponse:
    return _render(request, "job.html", job=_job(job_id))


@app.get("/jobs/{job_id}/progress")
def job_progress(request: Request, job_id: int) -> HTMLResponse:
    job = _job(job_id)
    # htmx stops polling on 286.
    return _render(request, "_job_progress.html", 200 if job.status == "running" else 286, job=job)
