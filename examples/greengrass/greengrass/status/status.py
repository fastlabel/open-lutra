"""Sends the device's OpenLUTRA status to CloudWatch metrics every INTERVAL seconds.

Metrics go to the OpenLUTRA namespace with a ThingName dimension, using the Token
Exchange Service credentials that Greengrass provides to the component. Heartbeat is
sent every time, so a device whose Heartbeat stops has stopped reporting.

Each finished recording whose validation has run is also reported once, at its start
time: RecordedSeconds is its duration and PassedSeconds the same duration when the
validation passed. The names already reported are kept in REPORTED_FILE in the
component's work directory, which survives restarts.
"""

import json
import os
import shutil
import time
import urllib.request
from datetime import UTC, datetime, timedelta

import boto3

NAMESPACE = "OpenLUTRA"
THING_NAME = os.environ["AWS_IOT_THING_NAME"]
INTERVAL = int(os.environ.get("STATUS_INTERVAL", "60"))
OPENLUTRA_URL = os.environ.get("OPENLUTRA_URL", "http://127.0.0.1:8000")
OUTPUT_DIR = os.environ["OUTPUT_DIR"]
REPORTED_FILE = "reported_recordings.json"
# CloudWatch rejects datapoints older than two weeks.
MAX_BACKFILL = timedelta(days=14)
DIMENSIONS = [{"Name": "ThingName", "Value": THING_NAME}]


def _get(path: str):
    with urllib.request.urlopen(f"{OPENLUTRA_URL}{path}", timeout=5) as response:
        return json.load(response)


def collect() -> dict[str, float]:
    disk = shutil.disk_usage(OUTPUT_DIR)
    metrics = {
        "Heartbeat": 1,
        "DiskFreePercent": disk.free / disk.total * 100,
        "DiskFreeGB": disk.free / 1024**3,
    }
    try:
        recording = _get("/api/recording/status")
        topics = _get("/api/topics")["topics"]
    except OSError as e:
        print(f"OpenLUTRA is not reachable: {e}", flush=True)
        metrics["OpenLutraUp"] = 0
        return metrics
    loss_rates = [t["loss_rate"] for t in topics if t.get("is_subscribed") and t.get("loss_rate") is not None]
    metrics["OpenLutraUp"] = 1
    metrics["Recording"] = 1 if recording["is_recording"] else 0
    metrics["MaxLossRate"] = max(loss_rates, default=0) * 100
    return metrics


def _load_reported() -> set[str]:
    try:
        with open(REPORTED_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def finished_recordings(reported: set[str]) -> list[dict]:
    """Datapoints for recordings not reported yet whose validation has finished."""
    oldest = datetime.now(UTC) - MAX_BACKFILL
    datapoints = []
    for entry in _get("/api/recordings")["entries"]:
        if entry["name"] in reported or not entry.get("validation_overall_status") or not entry.get("duration_ns"):
            continue
        started = datetime.fromtimestamp(entry["recording_start_ns"] / 1e9, UTC)
        seconds = entry["duration_ns"] / 1e9
        if started < oldest:
            reported.add(entry["name"])
            continue
        passed = seconds if entry["validation_overall_status"] == "pass" else 0
        datapoints.append({"name": entry["name"], "timestamp": started, "recorded": seconds, "passed": passed})
    return datapoints


def report_recordings(cloudwatch, reported: set[str]) -> None:
    for point in finished_recordings(reported):
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    "MetricName": name,
                    "Dimensions": DIMENSIONS,
                    "Timestamp": point["timestamp"],
                    "Value": value,
                    "Unit": "Seconds",
                }
                for name, value in (("RecordedSeconds", point["recorded"]), ("PassedSeconds", point["passed"]))
            ],
        )
        reported.add(point["name"])
    with open(REPORTED_FILE, "w") as f:
        json.dump(sorted(reported), f)


def main() -> None:
    units = {"DiskFreePercent": "Percent", "MaxLossRate": "Percent", "DiskFreeGB": "Gigabytes"}
    reported = _load_reported()
    cloudwatch = None
    while True:
        try:
            # Created inside the loop: right after boot the Token Exchange Service may not reach AWS yet
            # (e.g. DNS not up), and failing here would end the process; Greengrass marks a component
            # BROKEN after three quick failures and does not restart it.
            if cloudwatch is None:
                cloudwatch = boto3.client("cloudwatch")
            metrics = collect()
            cloudwatch.put_metric_data(
                Namespace=NAMESPACE,
                MetricData=[
                    {"MetricName": name, "Dimensions": DIMENSIONS, "Value": value, "Unit": units.get(name, "None")}
                    for name, value in metrics.items()
                ],
            )
            if metrics.get("OpenLutraUp"):
                report_recordings(cloudwatch, reported)
        except Exception as e:  # keep reporting on the next tick
            print(f"failed to send status: {e}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
