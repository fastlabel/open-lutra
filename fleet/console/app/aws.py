"""Read-only queries against Greengrass, IoT and ECR.

Writes (component versions, deployments) go through the make targets in jobs.py instead.
"""

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache

import boto3
from botocore.exceptions import ClientError

COMPONENT_NAME = os.environ["COMPONENT_NAME"]
# Written by greengrass/status/status.py.
METRIC_NAMESPACE = "OpenLUTRA"
MONITOR_WINDOW = timedelta(minutes=30)
OFFLINE_AFTER = timedelta(minutes=10)
DISK_FREE_WARNING_PERCENT = 5
DISK_DAYS_WARNING = 3
LOSS_WARNING_PERCENT = 2
# Why a device is not ok, with the condition each reason puts it in. The first four come from the
# status component's metrics (Monitoring.problems), the rest from Greengrass (Device.issues).
PROBLEMS = {
    "offline": ("No status received", "error"),
    "openlutra": ("OpenLUTRA not responding", "error"),
    "disk": ("Low disk space", "warning"),
    "loss": ("High loss rate", "warning"),
    "unhealthy": ("Device unhealthy", "error"),
    "stopped": ("OpenLUTRA not running", "error"),
    "deploy_failed": ("Deployment failed", "warning"),
    "version": ("Version differs from deployment", "warning"),
}
IMAGE_REPOSITORIES = ("open-lutra-backend", "open-lutra-frontend")
HISTORY_LIMIT = 20

_pool = ThreadPoolExecutor(max_workers=8)
# Group summaries fan out into _pool themselves, so they run on a separate pool to avoid starving it.
_group_pool = ThreadPoolExecutor(max_workers=4)

# Device conditions in display order: label, octicon and Primer color role for each.
CONDITIONS = {
    "ok": ("OK", "check-circle-fill", "success"),
    "updating": ("Updating", "sync", "accent"),
    "warning": ("Warning", "alert", "attention"),
    "error": ("Error", "x-circle-fill", "danger"),
}
IN_PROGRESS = ("QUEUED", "IN_PROGRESS")
_FAILED = ("FAILED", "TIMED_OUT", "REJECTED")


@dataclass
class Deployment:
    id: str
    group: str
    status: str
    created: datetime
    version: str
    configuration: str | None

    @property
    def recording_config(self) -> str | None:
        """The recording config content the deployment sent, if it sent one."""
        if not self.configuration:
            return None
        return json.loads(self.configuration).get("RecordingConfig")

    @property
    def recording_config_file(self) -> str | None:
        if not self.configuration:
            return None
        return json.loads(self.configuration).get("RecordingConfigFile")


@dataclass
class Monitoring:
    """Latest values the status component reported within MONITOR_WINDOW."""

    last_report: datetime | None = None
    disk_free_percent: float | None = None
    disk_free_gb: float | None = None
    recording: bool | None = None
    max_loss_rate: float | None = None
    openlutra_up: bool | None = None
    days_until_full: float | None = None

    @property
    def problems(self) -> list[str]:
        if self.last_report is None or datetime.now(UTC) - self.last_report > OFFLINE_AFTER:
            return ["offline"]
        found = []
        if self.openlutra_up is False:
            found.append("openlutra")
        if (self.disk_free_percent is not None and self.disk_free_percent < DISK_FREE_WARNING_PERCENT) or (
            self.days_until_full is not None and self.days_until_full <= DISK_DAYS_WARNING
        ):
            found.append("disk")
        if self.max_loss_rate is not None and self.max_loss_rate >= LOSS_WARNING_PERCENT:
            found.append("loss")
        return found


@dataclass
class Device:
    name: str
    health: str
    version: str | None
    state: str | None
    deployment_status: str | None
    monitoring: Monitoring = field(default_factory=Monitoring)

    def issues(self, expected_version: str | None) -> list[str]:
        """Reasons (keys of PROBLEMS) the device is not ok, errors first."""
        found = []
        if self.health != "HEALTHY":
            found.append("unhealthy")
        if self.state != "RUNNING":
            found.append("stopped")
        found += self.monitoring.problems
        if self.deployment_status in _FAILED:
            found.append("deploy_failed")
        elif self.deployment_status not in IN_PROGRESS and self.version != expected_version:
            # Left behind with no update coming, e.g. a cancelled deployment or a move to another group.
            found.append("version")
        return sorted(found, key=lambda kind: PROBLEMS[kind][1] != "error")

    def condition(self, expected_version: str | None) -> str:
        levels = {PROBLEMS[kind][1] for kind in self.issues(expected_version)}
        if "error" in levels:
            return "error"
        if "warning" in levels:
            return "warning"
        if self.deployment_status in IN_PROGRESS:
            return "updating"
        return "ok"


@dataclass
class DeviceDetail:
    name: str
    health: str
    last_seen: datetime | None
    nucleus_version: str | None
    platform: str | None
    architecture: str | None
    components: list[dict]
    deployments: list[dict]


@dataclass
class GroupSummary:
    name: str
    deployment: Deployment | None
    devices: list[Device]

    def updated(self) -> int:
        """Devices already running the version of the group's current deployment."""
        expected = self.deployment.version if self.deployment else None
        return sum(1 for d in self.devices if expected and d.version == expected)

    def counts(self) -> dict[str, int]:
        expected = self.deployment.version if self.deployment else None
        counts = dict.fromkeys(CONDITIONS, 0)
        for device in self.devices:
            counts[device.condition(expected)] += 1
        return counts


@cache
def _client(service: str):
    return boto3.client(service)


@cache
def _component_arn() -> str:
    region = boto3.session.Session().region_name
    account = _client("sts").get_caller_identity()["Account"]
    return f"arn:aws:greengrass:{region}:{account}:components:{COMPONENT_NAME}"


def _pages(service: str, operation: str, key: str, **kwargs) -> list[dict]:
    paginator = _client(service).get_paginator(operation)
    return [item for page in paginator.paginate(**kwargs) for item in page[key]]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def component_versions() -> list[str]:
    """Released component versions, newest first."""
    try:
        items = _pages("greengrassv2", "list_component_versions", "componentVersions", arn=_component_arn())
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return []
        raise
    versions = [item["componentVersion"] for item in items if re.fullmatch(r"\d+\.\d+\.\d+", item["componentVersion"])]
    return sorted(versions, key=_version_key, reverse=True)


def next_version(versions: list[str]) -> str:
    if not versions:
        return "0.1.0"
    major, minor, patch = _version_key(versions[0])
    return f"{major}.{minor}.{patch + 1}"


@cache
def image_tag(version: str) -> str | None:
    """IMAGE_TAG baked into a component version's recipe (versions are immutable, so cached).

    None when the version has been deleted, which old deployments in the history may still reference.
    """
    try:
        response = _client("greengrassv2").get_component(
            arn=f"{_component_arn()}:versions:{version}", recipeOutputFormat="JSON"
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise
    recipe = json.loads(response["recipe"])
    for manifest in recipe.get("Manifests", []):
        tag = manifest.get("Lifecycle", {}).get("Setenv", {}).get("IMAGE_TAG")
        if tag:
            return tag
    return None


def images_exist(tag: str) -> bool:
    for repository in IMAGE_REPOSITORIES:
        try:
            _client("ecr").describe_images(repositoryName=repository, imageIds=[{"imageTag": tag}])
        except ClientError as e:
            if e.response["Error"]["Code"] == "ImageNotFoundException":
                return False
            raise
    return True


def thing_groups() -> list[str]:
    return sorted(group["groupName"] for group in _pages("iot", "list_thing_groups", "thingGroups"))


@cache
def _group_arn(group: str) -> str:
    return _client("iot").describe_thing_group(thingGroupName=group)["thingGroupArn"]


def _to_deployment(summary: dict) -> Deployment | None:
    detail = _client("greengrassv2").get_deployment(deploymentId=summary["deploymentId"])
    component = detail.get("components", {}).get(COMPONENT_NAME)
    if component is None:
        return None
    return Deployment(
        id=summary["deploymentId"],
        group=summary["targetArn"].rsplit("/", 1)[-1],
        status=summary["deploymentStatus"],
        created=summary["creationTimestamp"],
        version=component["componentVersion"],
        configuration=component.get("configurationUpdate", {}).get("merge"),
    )


def deployments(group: str) -> list[Deployment]:
    """Deployments of the component to a group, newest first."""
    summaries = _pages(
        "greengrassv2", "list_deployments", "deployments", targetArn=_group_arn(group), historyFilter="ALL"
    )
    summaries.sort(key=lambda s: s["creationTimestamp"], reverse=True)
    return [d for d in _pool.map(_to_deployment, summaries[:HISTORY_LIMIT]) if d is not None]


def _core_devices(group: str) -> list[dict]:
    return _pages("greengrassv2", "list_core_devices", "coreDevices", thingGroupArn=_group_arn(group))


def groups() -> list[GroupSummary]:
    """All thing groups, with the latest deployment of the component where there is one."""
    summaries = _pages("greengrassv2", "list_deployments", "deployments", historyFilter="LATEST_ONLY")
    summaries = [s for s in summaries if ":thinggroup/" in s["targetArn"]]
    latest = {d.group: d for d in _pool.map(_to_deployment, summaries) if d is not None}

    def summarize(group: str) -> GroupSummary:
        return GroupSummary(group, latest.get(group), devices(group))

    return list(_group_pool.map(summarize, thing_groups()))


def _to_device(core_device: dict) -> Device:
    name = core_device["coreDeviceThingName"]
    installed = _pages("greengrassv2", "list_installed_components", "installedComponents", coreDeviceThingName=name)
    component = next((c for c in installed if c["componentName"] == COMPONENT_NAME), {})
    effective = _pages("greengrassv2", "list_effective_deployments", "effectiveDeployments", coreDeviceThingName=name)
    latest = max(effective, key=lambda d: d["modifiedTimestamp"], default={})
    return Device(
        name=name,
        health=core_device["status"],
        version=component.get("componentVersion"),
        state=component.get("lifecycleState"),
        deployment_status=latest.get("coreDeviceExecutionStatus"),
    )


def device(name: str) -> Device:
    found = _to_device(_client("greengrassv2").get_core_device(coreDeviceThingName=name))
    found.monitoring = _monitoring([name])[name]
    found.monitoring.days_until_full = days_until_disk_full([name]).get(name)
    return found


def devices(group: str) -> list[Device]:
    found = sorted(_pool.map(_to_device, _core_devices(group)), key=lambda d: d.name)
    names = [d.name for d in found]
    monitoring, days = _monitoring(names), days_until_disk_full(names)
    for device in found:
        device.monitoring = monitoring[device.name]
        device.monitoring.days_until_full = days.get(device.name)
    return found


_METRICS = {
    "Heartbeat": "SampleCount",
    "DiskFreePercent": "Average",
    "DiskFreeGB": "Average",
    "Recording": "Maximum",
    "MaxLossRate": "Maximum",
    "OpenLutraUp": "Minimum",
}


_cache: dict[tuple, tuple[float, object]] = {}
_cache_lock = threading.Lock()
# CloudWatch metrics have one-minute resolution, so polling pages share results for a minute; this also
# keeps GetMetricData requests (billed per metric) from growing with every open browser tab.
METRIC_CACHE_SECONDS = 60


def _cached(key: tuple, compute):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < METRIC_CACHE_SECONDS:
            return hit[1]
    value = compute()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def _metric_data(queries: list[dict], start: datetime, end: datetime) -> list[dict]:
    results = []
    for offset in range(0, len(queries), 500):
        paginator = _client("cloudwatch").get_paginator("get_metric_data")
        for page in paginator.paginate(
            MetricDataQueries=queries[offset : offset + 500], StartTime=start, EndTime=end, ScanBy="TimestampDescending"
        ):
            results.extend(page["MetricDataResults"])
    return results


def _query(query_id: str, thing: str, metric: str, stat: str, period: int) -> dict:
    return {
        "Id": query_id,
        "MetricStat": {
            "Metric": {
                "Namespace": METRIC_NAMESPACE,
                "MetricName": metric,
                "Dimensions": [{"Name": "ThingName", "Value": thing}],
            },
            "Period": period,
            "Stat": stat,
        },
    }


def _monitoring(things: list[str]) -> dict[str, Monitoring]:
    return _cached(("monitoring", tuple(things)), lambda: _fetch_monitoring(things))


def _fetch_monitoring(things: list[str]) -> dict[str, Monitoring]:
    result = {thing: Monitoring() for thing in things}
    if not things:
        return result

    queries = [
        _query(f"m{i}_{j}", thing, metric, stat, 60)
        for i, thing in enumerate(things)
        for j, (metric, stat) in enumerate(_METRICS.items())
    ]
    end = datetime.now(UTC)
    for series in _metric_data(queries, end - MONITOR_WINDOW, end):
        if not series["Values"]:
            continue
        i, j = (int(part) for part in series["Id"][1:].split("_"))
        monitoring, metric, value = result[things[i]], list(_METRICS)[j], series["Values"][0]
        if metric == "Heartbeat":
            monitoring.last_report = series["Timestamps"][0]
        elif metric == "DiskFreePercent":
            monitoring.disk_free_percent = value
        elif metric == "DiskFreeGB":
            monitoring.disk_free_gb = value
        elif metric == "Recording":
            monitoring.recording = value >= 1
        elif metric == "MaxLossRate":
            monitoring.max_loss_rate = value
        elif metric == "OpenLutraUp":
            monitoring.openlutra_up = value >= 1
    return result


def device_detail(name: str) -> DeviceDetail:
    client = _client("greengrassv2")
    core = client.get_core_device(coreDeviceThingName=name)
    components = _pages("greengrassv2", "list_installed_components", "installedComponents", coreDeviceThingName=name)
    effective = _pages("greengrassv2", "list_effective_deployments", "effectiveDeployments", coreDeviceThingName=name)
    return DeviceDetail(
        name=name,
        health=core["status"],
        last_seen=core.get("lastStatusUpdateTimestamp"),
        nucleus_version=core.get("coreVersion"),
        platform=core.get("platform"),
        architecture=core.get("architecture"),
        components=sorted(components, key=lambda c: c["componentName"] != COMPONENT_NAME),
        deployments=sorted(effective, key=lambda d: d["modifiedTimestamp"], reverse=True)[:HISTORY_LIMIT],
    )


VERSION_SLOTS = 6


def version_distribution(groups: list[GroupSummary]) -> list[tuple[str, int]]:
    """Devices per running component version, newest first; versions past VERSION_SLOTS fold into "Other"."""
    counts: dict[str, int] = {}
    for group in groups:
        for device in group.devices:
            version = device.version or "unknown"
            counts[version] = counts.get(version, 0) + 1

    def key(version: str) -> tuple[int, tuple[int, ...]]:
        return (1, _version_key(version)) if re.fullmatch(r"\d+\.\d+\.\d+", version) else (0, ())

    ordered = sorted(counts.items(), key=lambda item: key(item[0]), reverse=True)
    if len(ordered) <= VERSION_SLOTS:
        return ordered
    return ordered[: VERSION_SLOTS - 1] + [("Other", sum(n for _, n in ordered[VERSION_SLOTS - 1 :]))]


PERIODS = {"today": "Today", "week": "Last 7 days", "month": "Last 30 days"}


@dataclass
class Collection:
    """Recording hours by validation result, from the RecordedSeconds / PassedSeconds the status component sends."""

    buckets: list[tuple[str, float, float]]  # label, passed hours, other hours
    per_device: dict[str, tuple[float, float]]  # passed hours, recorded hours

    @property
    def passed_hours(self) -> float:
        return sum(passed for _, passed, _ in self.buckets)

    @property
    def recorded_hours(self) -> float:
        return sum(passed + other for _, passed, other in self.buckets)


def collection(things: list[str], period: str) -> Collection:
    return _cached(("collection", tuple(things), period), lambda: _fetch_collection(things, period))


def _fetch_collection(things: list[str], period: str) -> Collection:
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start = midnight
        keys = [start + timedelta(hours=h) for h in range(now.hour + 1)]
        label = lambda t: f"{t.hour}:00"
        bucket = lambda t: t.replace(minute=0, second=0, microsecond=0)
    else:
        days = 7 if period == "week" else 30
        start = midnight - timedelta(days=days - 1)
        keys = [start + timedelta(days=d) for d in range(days)]
        label = lambda t: f"{t.month}/{t.day}"
        bucket = lambda t: t.replace(hour=0, minute=0, second=0, microsecond=0)

    totals = {key: [0.0, 0.0] for key in keys}  # passed, recorded seconds
    per_device = {thing: [0.0, 0.0] for thing in things}
    queries = [
        _query(f"q{i}_{j}", thing, metric, "Sum", 3600)
        for i, thing in enumerate(things)
        for j, metric in enumerate(("PassedSeconds", "RecordedSeconds"))
    ]
    for series in _metric_data(queries, start, now) if queries else []:
        i, j = (int(part) for part in series["Id"][1:].split("_"))
        for timestamp, value in zip(series["Timestamps"], series["Values"], strict=True):
            key = bucket(timestamp.astimezone())
            if key in totals:
                totals[key][j] += value
                per_device[things[i]][j] += value
    return Collection(
        buckets=[
            (label(k), passed / 3600, max(recorded - passed, 0) / 3600) for k, (passed, recorded) in totals.items()
        ],
        per_device={thing: (passed / 3600, recorded / 3600) for thing, (passed, recorded) in per_device.items()},
    )


DISK_TREND_WINDOW = timedelta(days=3)


def days_until_disk_full(things: list[str]) -> dict[str, float | None]:
    """Days left at the rate free space fell over DISK_TREND_WINDOW; None when it is not falling."""
    return _cached(("disk", tuple(things)), lambda: _fetch_days_until_disk_full(things))


def _fetch_days_until_disk_full(things: list[str]) -> dict[str, float | None]:
    end = datetime.now(UTC)
    queries = [_query(f"d{i}", thing, "DiskFreeGB", "Average", 3600) for i, thing in enumerate(things)]
    result: dict[str, float | None] = dict.fromkeys(things)
    for series in _metric_data(queries, end - DISK_TREND_WINDOW, end) if queries else []:
        points = list(zip(series["Timestamps"], series["Values"], strict=True))
        if len(points) < 2:
            continue
        (latest_at, latest), (oldest_at, oldest) = points[0], points[-1]
        hours = (latest_at - oldest_at).total_seconds() / 3600
        per_day = (oldest - latest) / hours * 24 if hours else 0
        if per_day > 0.01:
            result[things[int(series["Id"][1:])]] = latest / per_day
    return result
