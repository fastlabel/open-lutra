# Quality Analysis

> Explains how the system evaluates the quality of recorded data, following the order of user operations.

## Table of contents

- [Overview](#overview)
- [1. Before recording: checking topics](#1-before-recording-checking-topics)
- [2. During recording: real-time monitoring](#2-during-recording-real-time-monitoring)
- [3. After recording: MCAP quality analysis](#3-after-recording-mcap-quality-analysis)
- [Detailed reference](#detailed-reference)

---

## Overview

For data to be usable as robot training data, **every topic must keep streaming at a stable rate**. Data drops and gaps directly hurt model accuracy.

This system lets you check quality in **three phases**:

| Phase | Purpose | What to verify |
|---|---|---|
| Before recording | Readiness check | Whether topics are streaming and rates are normal |
| During recording | Anomaly detection | Whether Hz is stable and gaps are not occurring |
| After recording | Final assessment | Whether the recorded data is usable for training |

---

## 1. Before recording: checking topics

Before pressing record, check that topics are streaming in the live topics list.

### What to check

| Item | Normal state | If abnormal |
|---|---|---|
| **Hz (frequency)** | `30/30Hz` (actual/baseline) | `0Hz` → not streaming |
| **Status dot** | Green (ok) | Yellow (warning) / Red (danger) |
| **Topic selection** | The topics you want to record are checked | Make sure nothing is missed |

> The Hz number is computed as described in [Frequency](#frequency).
> See [Baseline Hz](#baseline-hz) for how the baseline Hz is obtained.

---

## 2. During recording: real-time monitoring

Once recording starts, `TopicMonitor` (rclpy) streams quality data over SSE every second. The live topics list updates per-topic, a details panel appears when a topic is selected, and a loss-rate time series is plotted in the bottom tab.

> Post-recording quality reports are reviewed on the **Recordings list page (`/recordings`)** or the **MCAP detail page (`/recordings/:folder`)**.

### Per-topic quality display

Each topic row updates its status dot and quality info in real time.

**Display format:**

| State | Example | Meaning |
|---|---|---|
| Normal (fixed baseline) | `● 30/30Hz` | actual/baseline Hz |
| Abnormal (fixed baseline) | `● 88/100Hz 10.6% loss 10drop/s` | Drift from baseline + drop count visualized |
| Normal (dynamic learning) | `● 100/100Hz auto` | `auto` = dynamically learned |
| Learning | `● learning` | Baseline not yet determined |
| Data stalled | `● stalled` | No data for 3s+ |
| Idle | `● idle` | Never received |

`drop` is the number of missing messages over the last 5 seconds. It's computed from the same window as `loss_rate` (no additional cost).

> See [Quality status determination](#quality-status-determination) for the status-dot logic.
> See [Baseline Hz](#baseline-hz) for fixed vs. dynamically learned baselines.

### Topic Details (when a topic is selected)

Clicking a topic opens a detail dashboard.

| Item | Description |
|---|---|
| Quality bar | Progress bar showing `1 - loss_rate` |
| Drop heatmap | Last 30s of `loss_rate` visualized with 4 color bands (near-0% = light green, <2% = green, <5% = yellow, 5%+ = red). 0% uses a light background, so even small drops stand out visually |
| Stats summary | actual Hz, baseline Hz, drop/s, status, QoS, etc. |
| **Preview + Live** | Image topics: MJPEG stream (2fps normally / 30fps in Live). Sensor topics: position bar gauges (30fps) |
| Latest Message | Shows the latest message's JSON only when Live is OFF |

**Live mode**: toggled via the Live button in the Details header. Auto-stops after at most 1 minute. While Live is on, selecting another topic is disabled.

| Topic kind | Live display | Mechanism |
|---|---|---|
| Image (`*Image*`) | MJPEG stream (red border) | `/api/topics/image/stream` (2fps normally / 30fps in Live) |
| Sensor | Position bar gauges (red border) | Polls `/api/topics/live/positions` (30fps) |

### Loss Rate time-series graph (Loss Rate tab)

A real-time graph of loss rate rendered with uPlot. The Y axis is inverted (0% at the top = stable).

| Feature | Description |
|---|---|
| 30-second window | Shows the last 30s. Auto-scrolls to follow the right edge |
| Manual scroll | Mouse wheel to inspect past data. Snaps back to auto-follow when you return to the right edge |
| REC/STOP markers | Vertical lines at the moments recording starts/stops |
| warning/danger threshold lines | Dotted lines at 2% (yellow) and 5% (red) |
| Tooltip | Per-topic loss% on hover |
| Topic-selection linkage | When a topic is selected, only that topic is plotted; otherwise all topics |

**What to look for**: a flat line at 0% means stable. The further it dips, the worse. Crossing the warning/danger lines warrants attention.

### How real-time monitoring works

| Item | Details |
|---|---|
| Implementation | `TopicMonitor` (rclpy node) |
| Delivery | SSE `topic_stats` event (every 1s) |
| Gap detection | Emits a log immediately on occurrence (bottom Log tab) |

#### When each metric updates

| Metric | Update interval | Time to reflect | Description |
|---|---|---|---|
| `actual_hz` | 1s (SSE tick) | 3-4s window | Message count divided by the elapsed time of the current counting window |
| `baseline_hz` (fixed) | Immediate | Right after subscribe | Uses the YAML value as-is |
| `baseline_hz` (dynamic) | One-shot | ~4s after the first message | 1s warmup, then locked in once the measurement spans 3s and 50 messages (topics slower than ~17Hz wait for the 50th sample) |
| `loss_rate` | 1s (SSE tick) | 5s window | Difference between expected and actual counts over the last 5s |
| `drop_count` | 1s (SSE tick) | 5s window | Computed alongside `loss_rate` (expected - actual) |
| `status` | 1s (SSE tick) | Immediate | `danger` requires a 3s stall |
| `gap` | Immediate | On message receipt | Detected and logged when the previous receive was >3s ago |

---

## 3. After recording: MCAP quality analysis

After recording stops, `MCAPAnalyzer` analyzes every message in the MCAP file and produces an accurate report.

Per-recording quality summaries are reviewed on the **Recordings list page (`/recordings`)**, and drop locations on the timeline and Joint graphs are reviewed on the **MCAP detail page (`/recordings/:folder`)**.

### MCAP quality report

Selecting a recording shows the quality report. While analysis is running, an "Analyzing quality..." spinner is shown.

#### Per-topic quality table

A table view of each topic's quality.

**Always visible (collapsed view)**:

| Item | Example | When shown | Details |
|---|---|---|---|
| Status | 🟢 / 🟡 / 🔴 | Always | Based on loss rate and continuity score |
| Topic name | `/joint_states` | Always | - |
| Frequency | `100.0Hz` | Always | → [Frequency](#frequency) |
| Message type | `JointState` | Always | - |
| Message count | `8,222 msgs` | Always | - |
| Loss rate | `0.1% miss` | Always | → [Loss rate](#loss-rate) |
| Continuity score | `99 score` | Always | → [Data continuity score](#data-continuity-score) |
| Start delay | `+0.1s delay` | ≥ 0.1s | → [Start delay / early end](#start-delay--early-end) |
| Empty frames | `3 empty` | ≥ 1 | → [Message size statistics](#message-size-statistics) |
| Gap count | `3 gaps` | ≥ 1 | → [Gaps](#gaps) |

**Expanded (click to show)**:

| Item | Example | When shown | Details |
|---|---|---|---|
| Size statistics | `Size: 100B ~ 200B (avg 150B ±30B)` | Always | → [Message size statistics](#message-size-statistics) |
| Start delay | `Start +0.10s` | ≥ 0.1s | → [Start delay / early end](#start-delay--early-end) |
| Early end | `End -0.50s` | ≥ 0.1s | → [Start delay / early end](#start-delay--early-end) |
| Gap list | `42.0s gap 0.13s` | ≥ 1 | → [Gaps](#gaps) |

### Loss Rate chart (MCAP detail page)

The **QUALITY ANALYTICS** tab on `/recordings/:folder` renders a per-topic loss% time series with uPlot. The Y axis is inverted (0% on top = stable); the warn/danger threshold lines (2% / 5%) match the rest of the quality visualization (see [Quality status determination](#quality-status-determination)). The axis keeps a `[0, 10]%` window for the common near-zero case and auto-expands when a topic runs far below its rate, so a large sustained deficit stays on-screen.

**Input**: per-topic timeline bins produced by `TimelineAnalyzer`. Each bin carries `count` (received) and `expected` (frames expected in the bin); `expected` already reflects the configured `expected_hz` when set (see [Baseline Hz](#baseline-hz)).

**Algorithm**: count-based deficit over a 1-second sliding window with a 0.1-second step, centered on each sample point.

Each sample point `x = i × STEP_SEC` represents the loss% inside the window `[x − WINDOW_SEC/2, x + WINDOW_SEC/2)` centered on `x`:

```
received_in_window = Σ bin.count      # over bins overlapping the window
expected_in_window = Σ bin.expected
loss_rate(x)       = min(100, max(0, 1 − received_in_window / expected_in_window) × 100)
```

This mirrors the per-topic `loss_rate` in the quality report, so a stream running steadily below its configured rate shows a sustained plateau here (e.g., a 100 Hz-configured topic delivering ~72 Hz plots a flat ~28% line) — not just the discrete IQR dropouts. Those dropouts remain visible as the `minor` / `major` counts and as gap markers on the Timeline heatmap.

| Parameter | Value | Role |
|---|---|---|
| `WINDOW_SEC` | 1.0 s | Aggregation-window width. The denominator (`Σ bin.expected ≈ expected_hz × WINDOW_SEC`) keeps the 2% / 5% thresholds meaningful across the quality stack. |
| `STEP_SEC` | 0.1 s | Spacing between sample points. |

**How to read the chart**:

- **A steady under-rate appears as a sustained plateau** at the deficit level (received vs expected).
- **A localized dropout appears as a ~1-second-wide "bump"** centered on when it occurred (its bins fall short for the windows overlapping them).

Implementation: `frontend/src/features/quality-timeline/loss-rate-utils.ts`.

### How MCAP analysis works

| Item | Details |
|---|---|
| Implementation | `MCAPAnalyzer` (mcap Python library) |
| Data source | All message timestamps inside the MCAP file |
| Expected Hz | Config-declared `expected_hz_patterns` value when the topic matches; otherwise the nearest standard frequency estimated from message intervals |
| Accuracy | More accurate than real-time monitoring (uses the full data, not an approximation) |
| Persistence | Saved as `quality_report.json` in the same directory as the MCAP (cache) |
| Execution | Runs in the background via `asyncio.to_thread()` (does not block the UI) |

---

## Detailed reference

The metrics and decision logic referenced by the phases above.

### Frequency

**Used in**: pre-recording Hz display, in-recording graph/badges, post-recording topic details

| Metric | Window | Description | Example |
|---|---|---|---|
| `actual_hz` | 3s (tumbling) | Counter-based (O(1)) for every topic, regardless of how the baseline was obtained | 92.0 Hz |
| `baseline_hz` | - | Baseline frequency. From YAML config (fixed) or dynamically learned (locked in ~4s after the first message) | 100.0 Hz |

```python
# Messages counted since the window opened, over monotonic elapsed time
actual_hz = hz_count / (now - hz_count_start)
```

The window is **tumbling**, not sliding: it is discarded and restarted once it
exceeds 3s, so the effective width depends on how often `refresh_cache` runs
(3-4s at the 1s SSE tick). While a freshly opened window holds less than 0.5s of
data the previous value is reported, which keeps a healthy topic from briefly
reading 0Hz. Because counting is driven by `time.monotonic()` rather than by
message timestamps, a topic whose publisher stops decays to 0Hz instead of
freezing at its last value; at the 1s SSE tick it reaches exactly 0 within
about 1-5 seconds, depending on where the stall lands in the window.

### Baseline Hz

**Used in**: as the basis for loss rate and quality-status decisions

There are two ways to obtain the baseline Hz, controlled via the YAML config file (`config/*.yaml`).

| Mode | Setting | UI display | Description |
|---|---|---|---|
| **Fixed** | `hz: 100` | `88/100Hz` | Uses the YAML value immediately. High reliability |
| **Dynamic learning** | `hz:` (omitted) | `100/100Hz auto` | After subscribe, auto-derived from the measured arrival rate |

```yaml
# config/simulator.yaml (or your own config)
expected_hz_patterns:
  - pattern: "**/compressed"
    hz: 30              # Fixed: use 30Hz as the quality baseline
  - pattern: "/sensor/*" # Dynamic learning: derive the baseline from measured values
```

**How dynamic learning works**:

1. For 1 second after the first message, nothing is measured (lets the DDS initial burst settle)
2. The message count and clock are then snapshotted, and the measurement runs from that point
3. Once the measurement spans 3 seconds **and** 50 messages, the rate locks in as `baseline_hz` (50 samples bound the ±1-message counting error to ~2%, matching the loss-rate thresholds)

The measurement is a snapshot delta over the append-only message counter, so it
is unaffected by how often stats are polled. Learning advances on the stats
tick (SSE stream / `GET /api/topics`), so it progresses only while stats are
being polled — harmless, since the learned value is consumed by those same
polls.

**Operational flow**: start unknown topics with dynamic learning (`hz:` omitted), confirm the stable value in the UI, then write it back to YAML as a fixed value.

**Behavior of `reset_baseline`** (`POST /api/topics/reset-baseline`):

| Baseline kind | Behavior |
|---|---|
| Fixed (YAML config) | Keeps `baseline_hz`. Only resets timing-related metrics |
| Dynamic learning | Sets `baseline_hz` back to `None` and restarts learning (warmup + measurement) |

**Scope**: `expected_hz_patterns` is referenced by both live monitoring (Phase 2) and post-recording MCAP analysis (Phase 3). In Phase 3 a matching `hz` overrides the auto-estimated expected Hz for that topic — it becomes the topic's `expected_frequency_hz` and drives the loss-rate denominator, the gap/loss detection thresholds, and the timeline's expected Hz. Topics with no matching `hz` (pattern omitted or `hz:` left blank) fall back to statistical re-estimation from timestamps (see [How MCAP analysis works](#how-mcap-analysis-works)).

### Loss rate

**Used in**: in-recording quality display, post-recording topic details
**Window**: 5s sliding (resets every 5s)
**Update timing**: SSE tick (every 1s)

How much the actual received message count falls short of the expected count over the last 5 seconds. The computation is switched via `stamp_quality` in YAML.

**Count-based** (`stamp_quality: false`, for the simulator):

```
expected_count = baseline_hz × elapsed_sec   (elapsed ≤ 5s)
loss_rate      = 1 - (actual_count / expected_count)
drop_count     = expected_count - actual_count
```

**Stamp-based** (`stamp_quality: true`, for real robots): directly counts missing frames from `header.stamp` intervals. Gaps exceeding **1.5x** the expected interval are treated as losses, adding `round(interval / expected_interval) - 1` to the loss count (below 1.5x is treated as jitter and ignored).

```
expected_interval = 1.0 / baseline_hz
if interval > expected_interval × 1.5:
    loss_count += round(interval / expected_interval) - 1
loss_rate = loss_count / (msg_count + loss_count)
```

Since the simulator's `header.stamp` contains OS-timer jitter, stamp-based mode is not usable there. On a real robot, the stamp comes from a hardware clock and has very little jitter, so stamp-based is more accurate (it eliminates DDS delivery jitter).

`loss_rate` and `drop_count` are computed in the same pass from the same window (no extra cost).
`drop_count` is normalized to per-second, so it is directly comparable to `baseline_hz` (e.g., at 100Hz with 10 drop/s, that's a 10% loss).

| Metric | UI display | Condition |
|---|---|---|
| `loss_rate` | `10.6% loss` (2%~ yellow, 5%~ red) | Shown when above 2% |
| `drop_count` | `10drop/s` (yellow) | Shown at 1/s or more |

When state changes (e.g., unstable→stable), the new value is reflected within 5 seconds.

### Data continuity score

**Used in**: in-recording badge decisions, post-recording topic details

Whether data is continuous without gaps (0.0-1.0). Total gap time deducts from the score.

```
continuity = 1.0 - (gap_total_sec / topic_duration)
```

| continuity | Meaning |
|---|---|
| 1.000 | Fully continuous (no gaps) |
| 0.990 | 1% of the time has data drops → ok (minor) |
| 0.980 | 2% of the time has data drops → warning |
| 0.900 | 10% of the time has data drops → danger |

### Gaps

**Used in**: in-recording log output, post-recording topic details

A blank period exceeding 3x the expected interval.

```
gap_threshold = expected_interval × 3.0
```

Example: on a 100Hz topic (expected interval 10ms), any blank of 30ms or more is detected as a gap.

Each gap carries:
- `timestamp_sec`: seconds since recording started
- `duration_sec`: length of the gap

### Message size statistics

**Used in**: post-recording topic details (expanded view)

| Metric | Description |
|---|---|
| `min_bytes` | Smallest message size |
| `max_bytes` | Largest message size |
| `avg_bytes` | Average message size |
| `std_bytes` | Size standard deviation |
| `zero_size_count` | Number of zero-size messages (potentially abnormal frames) |

### Start delay / early end

**Used in**: post-recording topic details (expanded view)

| Metric | Description |
|---|---|
| `start_delay_sec` | Delay from recording start to this topic's first message |
| `end_early_sec` | Blank from this topic's last message to the recording end |

### Quality status determination

**Used in**: each topic row in the MCAP quality report (green/yellow/red)

Each topic is assigned `ok` / `warning` / `danger`. Decided based on loss_rate and LossEvent:

```python
def _determine_status(major_loss: int, minor_loss: int, msg_count: int, loss_count: int) -> str:
    if msg_count == 0:
        return "ok"               # No messages → out of scope
    loss_rate = loss_count / (msg_count + loss_count)
    if loss_rate > 0.05 or major_loss > 0:
        return "danger"           # >5% loss or 3+ consecutive frame drops → red
    if loss_rate > 0.02 or minor_loss > 0:
        return "warning"          # >2% loss or 1-2 frame drops → yellow
    return "ok"                   # No loss → green
```

The timeline heatmap, Loss Rate graph, and Quality Details color coding are **all unified** (the same green/yellow/red 3-level scheme).

#### Live-monitoring status decision

During recording, the live monitor (per-topic status dot) uses a separate logic from the post-recording MCAP analysis. It uses only `baseline_hz` and the most recent receive time, so it is O(1) and lightweight:

| Status | Condition |
|---|---|
| `inactive` | `message_count == 0` (never received) |
| `danger` | More than `gap_threshold_sec` (default 3.0s) since the last receive |
| `warning` | `actual_hz < baseline_hz × 0.5` (`_hz_drop_threshold = 0.5`) |
| `ok` | None of the above |

`hz_drop_threshold` is a field on `TopicStats` but currently is not configurable via YAML / env vars (it's hardcoded to the default `0.5`). MCAP post-analysis is IQR + LossEvent based and produces a more detailed judgment.
