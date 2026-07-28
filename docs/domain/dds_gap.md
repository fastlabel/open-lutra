# Message Gaps in DDS Communication

> A systematic explanation of why messages get lost or delayed over DDS (Data Distribution Service) communication.
> A reference for diagnosing and tuning data quality.
>
> Related: [Quality analysis](quality_analysis.md)

## Prerequisites

ROS2 messaging runs on top of a communication middleware called **DDS (Data Distribution Service)**. DDS uses the **RTPS (Real-Time Publish-Subscribe)** protocol to implement pub-sub communication over **UDP/IP**.

```
ROS2 Node (Publisher)
    │
    ▼
rmw (ROS Middleware) layer  ← rclpy / rclcpp abstract this away
    │
    ▼
DDS implementation (Cyclone DDS / Fast DDS / Connext)
    │
    ▼
RTPS protocol  ← Reliability via Heartbeat / ACKNACK
    │
    ▼
UDP/IP (or Shared Memory)
    │
    ▼
ROS2 Node (Subscriber / ros2 bag record)
```

This project uses **ROS2 Humble + Fast DDS** (`rmw_fastrtps_cpp`, the Humble default; pinned via `RMW_IMPLEMENTATION` in `docker-compose.yml`). Recording is done by running `ros2 bag record -s mcap` in a subprocess.

Sections below that describe implementation-specific defaults name the implementation they apply to. Cyclone DDS values are kept as comparison reference and do **not** describe this project's runtime.

---

## 1. RTPS protocol reliability mechanism

### 1.1 Retransmission via Heartbeat / ACKNACK

To deliver "reliable communication" over an unreliable transport like UDP, RTPS has a **NACK-based retransmission mechanism**.

```
DataWriter                              DataReader
    |                                       |
    |--- DATA (seq=1) ───────────────►     |
    |--- DATA (seq=2) ────── ✗ (lost)      |  ← UDP packet lost on the network
    |--- DATA (seq=3) ───────────────►     |
    |                                       |
    |--- HEARTBEAT (1-3) ──────────►       |  ← "I've sent seq 1-3"
    |                                       |
    |◄── ACKNACK (missing: {2}) ────       |  ← "I never received seq=2"
    |                                       |
    |--- DATA (seq=2) ───────────────►     |  ← Retransmit
    |                                       |
    |◄── ACKNACK (all received) ────       |  ← Confirms receipt of all
    |                                       |
    |  (Released from Writer History Cache) |
```

**Important RTPS submessages:**

| Submessage | Direction | Role |
|---|---|---|
| **DATA** | Writer → Reader | Data sample, identified by a sequence number |
| **HEARTBEAT** | Writer → Reader | Tells the reader the range of sent sequence numbers and asks for an ack |
| **ACKNACK** | Reader → Writer | Bitmap of received/unreceived sequence numbers |
| **GAP** | Writer → Reader | Tells the reader that a specific sample is not in the writer's queue |

### 1.2 Writer History Cache (WHC)

The writer keeps sent data in the **WHC (Writer History Cache)** so it can retransmit on request. Once all readers have acked a sample, it is released from the WHC.

**Cyclone DDS WHC defaults:**

| Parameter | Default | Description |
|---|---|---|
| `WhcHighInit` | 30 kB | Initial high-water mark for the WHC |
| `WhcHigh` | 500 kB | Upper bound for the dynamically adjusted high-water mark |
| `WhcLow` | 1 kB | Low-water mark for the WHC |
| `WhcAdaptive` | true | Adapt the high-water mark based on send pressure and retransmission requests |

**Behavior when the WHC overflows:**
- KEEP_LAST: Old samples get overwritten by new ones → **data loss**
- KEEP_ALL: The writer blocks (new `write()` calls wait) → the publisher stalls

### 1.3 Heartbeat timing

The heartbeat period directly affects how fast a loss is detected.

**Cyclone DDS:**

| Parameter | Default |
|---|---|
| HeartbeatInterval (base) | 100 ms |
| HeartbeatInterval (min) | 5 ms |
| HeartbeatInterval (max) | 8 s |
| NackDelay | 100 ms |

**RTPS spec defaults:**

| Parameter | Default |
|---|---|
| nackResponseDelay | 200 ms |
| heartbeatResponseDelay | 500 ms |

→ From the moment a loss occurs to the moment retransmission completes, you can see anywhere from a few **hundred ms to several seconds** of delay. For high-rate data (200Hz), more data piles up during that delay, possibly overflowing the WHC.

---

## 2. QoS policies and gaps

### 2.1 Reliability — the biggest influence

| Setting | Behavior | Effect on gaps |
|---|---|---|
| **BEST_EFFORT** | No retransmit. Lost samples are gone forever | Packet loss = immediate gap |
| **RELIABLE** | Attempts recovery via Heartbeat/ACKNACK/retransmit | Can recover via retransmit, but with limits (see below) |

**Cases where messages are still lost under RELIABLE:**
1. **Buffer overflow with KEEP_LAST**: Once history depth is exceeded, old samples get overwritten
2. **WHC overflow**: The writer's retransmission buffer fills up and discards samples
3. **`max_heartbeat_retries` reached**: The reader is declared inactive after the default 10 retries
4. **Listener blocking**: Long-running work inside a callback stalls the receive thread, overflowing socket buffers
5. **`max_blocking_time` reached**: The writer's `write()` cannot enqueue within the allotted time and the message is dropped (unrecoverable)

### 2.2 Reliability compatibility rules

| Publisher | Subscriber | Connects | Notes |
|---|---|---|---|
| RELIABLE | RELIABLE | **OK** | Retransmit available. Most reliable |
| RELIABLE | BEST_EFFORT | **OK** | Subscriber accepts a lower quality, so it's compatible |
| BEST_EFFORT | RELIABLE | **NG** | Subscriber asks for retransmit, publisher cannot offer it |
| BEST_EFFORT | BEST_EFFORT | **OK** | No retransmit. Lightest |

**Compatibility rule of thumb**: Connection fails only when the subscriber's "request" is stricter than the publisher's "offer". RELIABLE pub + BEST_EFFORT sub is "high offer, low request", so it's OK.

### 2.3 History

| Setting | Effect on gaps |
|---|---|
| **KEEP_LAST (depth=N)** | Once the buffer exceeds `depth`, old messages are silently discarded. Small depths cause frequent losses on high-rate topics |
| **KEEP_ALL** | Tries to keep every message, bounded by Resource Limits. RELIABLE + KEEP_ALL risks blocking the writer and stalling the publisher |

**Effect of `depth` (for a 100Hz topic):**

| depth | Buffer time | Tolerable processing delay |
|---|---|---|
| 1 | 10ms | Almost none |
| 10 (default) | 100ms | Up to 0.1s of delay |
| 100 | 1000ms | Up to 1s of delay |
| 1000 | 10000ms | Up to 10s of delay |

If the subscriber (ros2 bag record) is temporarily blocked on disk writes, a small `depth` causes immediate message drops.

### 2.4 Durability

| Setting | Effect on gaps |
|---|---|
| **VOLATILE** | Past data is not sent to late joiners. Any message published before recording starts is lost |
| **TRANSIENT_LOCAL** | While the writer is alive, past data is sent to late joiners. Mitigates the late-joiner problem |

**Compatibility:**

| Publisher | Subscriber | Connects |
|---|---|---|
| VOLATILE | VOLATILE | OK |
| VOLATILE | TRANSIENT_LOCAL | **NG** |
| TRANSIENT_LOCAL | VOLATILE | OK (connects, but past data is not delivered) |
| TRANSIENT_LOCAL | TRANSIENT_LOCAL | OK |

### 2.5 Deadline

- Publisher: obligated to publish samples within the deadline period
- Subscriber: expects samples within the deadline period
- A deadline miss is reported via callback, but **messages are not auto-recovered**
- Useful to *detect* gaps, not to *prevent* them

### 2.6 Liveliness

| Mode | Behavior |
|---|---|
| AUTOMATIC (default) | DDS middleware renews the lease automatically. Alive as long as the process exists |
| MANUAL_BY_PARTICIPANT | The application asserts liveliness explicitly |
| MANUAL_BY_TOPIC | Asserted per DataWriter. Strictest |

A node is declared "dead" if liveliness is not asserted within the lease period. If a publisher hangs, **it is not detected until the lease expires**.

### 2.7 Resource Limits

| Parameter | Description |
|---|---|
| `max_samples` | Maximum total samples in the writer/reader queue |
| `max_instances` | Maximum instances (for keyed topics) |
| `max_samples_per_instance` | Maximum samples per instance |

Under KEEP_ALL, Resource Limits are the de facto upper bound. New samples are rejected once they're hit.

### 2.8 Lifespan

The expiration period for a message. Expired messages are automatically removed from the writer/reader. If network or processing delay pushes a message past its lifespan, it is discarded even if received.

---

## 3. Patterns that cause gaps

### 3.1 Network layer

#### Packet loss (UDP)

```
Normal:   #1 ── #2 ── #3 ── #4 ── #5
Loss:     #1 ── #2 ── ✗  ── #4 ── #5
                      #3 lost on the network
```

- DDS runs on UDP, so it is directly affected by packet loss
- BEST_EFFORT: unrecoverable
- RELIABLE: tries to recover via retransmit, but the recovery introduces delay

#### IP fragmentation issues

Messages larger than the MTU (typically 1500 bytes) are fragmented at the IP layer. **If one fragment is lost, the remaining fragments occupy the kernel buffer**, and Linux defaults to retrying reassembly for 30 seconds. During that time, new fragments cannot be accepted and communication "hangs".

```
1MB image message → about 700 IP fragments
  → One lost fragment fails the whole message
  → The buffer is jammed for 30 seconds → cascading losses on following messages
```

**Fix**: shorten `net.ipv4.ipfrag_time` to 3 seconds (see the tuning section below)

#### Network congestion

- Bandwidth exceeded on multicast/unicast
- Switch buffer overflow
- When multiple cameras (30Hz × 4) + JointState (200Hz) all communicate simultaneously, bandwidth can be tight

### 3.2 Publisher side

#### Scheduling delay

```
At 200Hz (expected interval 5ms):

Normal:    │5ms│5ms│5ms│5ms│5ms│
Delayed:   │5ms│5ms│  16ms  │4ms│5ms│
                     ↑
           Another process takes the CPU → scheduling slips
```

- On standard Linux (the CFS scheduler), thread-switching granularity is coarse and high-rate publishes have jitter
- Above 200Hz, the OS scheduling resolution (1ms-10ms) becomes a non-negligible fraction of the inter-message interval

#### Driver/hardware pauses

```
│5ms│5ms│    500ms          │5ms│5ms│
            ↑
  Camera driver can't reserve USB bandwidth and pauses
  Robot controller enters an error state and recovers
```

- Hardware devices pausing or recovering from errors
- USB bandwidth contention
- Internal errors in the robot controller

#### `write()` blocking

Under RELIABLE + KEEP_ALL + TRANSIENT_LOCAL, hitting Resource Limits blocks the `write()` call. The publisher itself can no longer send.

### 3.3 Subscriber side

#### Buffer overflow (most important for ros2 bag record)

```
Publisher (200Hz)           ros2 bag record
    │                           │
    ├── DATA ──────────►  DDS buffer (KEEP_LAST depth=10)
    ├── DATA ──────────►    │ ← writing to disk...
    ├── DATA ──────────►    │
    ├── DATA ──────────►    │ ← buffer full, old messages discarded
    ├── DATA ──────────►    │
    ...                     │
                           disk write completes
                           → resumes from the next message (gap)
```

**ros2 bag record data flow:**

```
DDS receive buffer (depth=N)
    │
    ▼
rosbag2 internal cache (CircularMessageCache, max_cache_size)
    │
    ▼
Storage plugin (MCAP Writer)
    │
    ▼
Disk I/O
```

Buffer overflow at any stage drops messages.

#### Disk I/O bottleneck

- The **biggest source** of message loss in rosbag2
- When writes can't keep up, the cache buffer overflows and messages are discarded
- An SSD is strongly recommended. With an HDD, high-bandwidth recording reliably loses data
- The recorder logs "number of messages dropped from the cache buffer" on shutdown

#### Executor processing delay

If the ROS2 executor can't keep up with the callback queue, old messages are silently discarded under KEEP_LAST.

### 3.4 DDS discovery

#### Message loss before discovery completes

```
(ros2 bag record starts)
    │
    ├── SPDP: discover DomainParticipants  (~1s)
    ├── SEDP: get DataWriter QoS  (~few hundred ms)
    ├── Create DataReader
    │
    │   Every message during this period is lost
    │
    ├── Start receiving
```

This project addresses this by starting the recording process with `--start-paused` and resuming after discovery completes. On top of that, `recording_start_delay_sec` (YAML setting) lets you add **extra wait after discovery completes**. Camera drivers like RealSense have an extra ~1 second of ramp-up before the first frame after subscribe is confirmed, so `--start-paused` alone leaves a camera-empty period at the start of the recording. Setting `recording_start_delay_sec: 2.0` waits for that ramp-up before sending SPACE, eliminating the empty period at the start.

#### QoS auto-detection race condition

`ros2 bag record` auto-detects publisher QoS and adapts, but there is a **race condition**:

1. Topic is discovered
2. Try to fetch the DataWriter's QoS
3. QoS info hasn't arrived yet → subscribe with the default (RELIABLE)
4. The actual publisher is BEST_EFFORT → **QoS mismatch, connection fails**

Reported frequency: "3-4 out of 10 recording sessions" ([rosbag2 #967](https://github.com/ros2/rosbag2/issues/967)).

This project avoids the issue by pre-detecting the publisher's QoS in TopicMonitor and explicitly passing it via `--qos-profile-overrides-path`.

#### Multicast join timing

When the network has no multicast router, IGMP queries are not sent, the switch's IGMP Snooping group times out, and the switch can drop multicast packets.

### 3.5 Inside the DDS middleware

#### Buffer limits inside the middleware (Cyclone DDS values, for reference)

| Parameter | Default | Effect on overflow |
|---|---|---|
| `DefragReliableMaxSamples` | 16 | Concurrent fragment reassemblies above 16 cause data loss |
| `DefragUnreliableMaxSamples` | 4 | Concurrent BEST_EFFORT defrag limit |
| `DeliveryQueueMaxSamples` | 256 | The receive→delivery thread queue backs up |
| `MaxQueuedRexmitMessages` | 200 | Retransmission queue limit |
| `MaxQueuedRexmitBytes` | 512 kB | Retransmission queue byte limit |

#### Notes on Shared Memory Transport

Fast DDS enables Shared Memory Transport by default for same-host communication, but Cyclone DDS does not. Since this project runs on Fast DDS, same-host traffic (simulator ↔ backend on the same Docker host) can take the **SHM path rather than UDP**.

SHM avoids network-layer issues (IP fragmentation, UDP buffer overflow) entirely, but gaps can still occur in cases such as:
- Segment size shortfall: when `segment_size` is close to the data size, the buffer is overwritten
- Ring buffer overflow: if the reader is slow, descriptors are overwritten

---

## 4. Risk analysis by frequency

### 4.1 Gap thresholds and concerns per frequency

This project's gap detection uses a threshold of "more than 3x the expected interval" (`_GAP_MULTIPLIER = 3.0`).

| Hz | Expected interval | Gap threshold (×3) | Main risks |
|---|---|---|---|
| **30** | 33.3ms | 100ms | Can't detect 1-2 frame drops. For images, even a single dropped frame (66ms) can hurt learning |
| **100** | 10ms | 30ms | Well balanced. 30ms is a realistic threshold |
| **200** | 5ms | 15ms | OS jitter (1-10ms) can cross the threshold. Real loss is hard to distinguish from jitter |
| **500** | 2ms | 6ms | Comparable to OS scheduling resolution. **Frequent false positives** likely |

### 4.2 Issues at 30Hz (cameras)

```
30Hz, expected interval 33.3ms, gap threshold 100ms

1-frame drop:
  │33ms│33ms│  66ms  │33ms│  ← 66ms < 100ms → not detected
                ↑
      One frame missing. For a camera image,
      a moment of the robot's motion is unrecorded

2 consecutive drops:
  │33ms│33ms│  99ms  │33ms│  ← 99ms < 100ms → still not detected

3 consecutive drops:
  │33ms│33ms│  132ms │33ms│  ← 132ms > 100ms → finally detected
```

### 4.3 Issues at 200Hz (JointState)

```
200Hz, expected interval 5ms, gap threshold 15ms

Normal OS jitter:
  │4.8│5.2│4.5│5.5│  ← All under 15ms → OK

OS scheduling delay (no actual loss):
  │5ms│5ms│ 16ms │4ms│5ms│  ← 16ms > 15ms → false positive!
                ↑
      No message was actually dropped.
      The previous one came slightly early and the next slightly late.
```

### 4.4 Accumulation of small sporadic losses

```
200Hz, gap threshold 15ms

  │5│5│5│ 14ms │5│5│5│ 14ms │5│5│5│ 14ms │5│5│
            ↑           ↑           ↑
  Each 14ms < 15ms → none detected as gaps
  But overall, 3 × ~1 message = 3 messages lost
  → loss_rate reflects this, but gap_count is 0
```

---

## 5. ROS2 default QoS profiles

### 5.1 Preset profiles

| Profile | Reliability | Durability | History | Depth | Use case |
|---|---|---|---|---|---|
| **Default** | RELIABLE | VOLATILE | KEEP_LAST | 10 | General pub/sub |
| **Sensor Data** | BEST_EFFORT | VOLATILE | KEEP_LAST | 5 | Sensor data (camera, LiDAR) |
| **Services** | RELIABLE | VOLATILE | KEEP_LAST | 10 | Service communication |
| **Parameters** | RELIABLE | VOLATILE | KEEP_LAST | 1000 | Parameters |
| **System Default** | Depends on RMW | Depends on RMW | Depends on RMW | - | Delegates to the DDS default |

### 5.2 Typical QoS by message type

The message type itself doesn't carry a QoS. QoS is set in the publisher/subscriber code.

| Topic kind | Common QoS | Notes |
|---|---|---|
| **Image / CompressedImage** | REP-2003 recommends Sensor Data (BEST_EFFORT) | But image_transport defaults to RELIABLE, which is a common source of mismatch |
| **JointState** | Often Default (RELIABLE) | Depends on the robot driver |
| **/tf** | Default (RELIABLE) | Needed for frame-transform consistency |
| **/tf_static** | RELIABLE + TRANSIENT_LOCAL, KEEP_ALL | To serve late joiners |
| **/clock** | BEST_EFFORT, KEEP_LAST depth=1 | Only the most recent value matters |

### 5.3 Diagnosing QoS mismatches

```bash
# Check the publisher's QoS
ros2 topic info /topic_name --verbose

# QoS compatibility check
ros2 doctor --report
# → QOS COMPATIBILITY LIST shows the compatibility state

# Confirm the subscriber is connected
ros2 topic info /topic_name
# → Subscription count: 0 ← may have failed to subscribe
```

---

## 6. Issues specific to ros2 bag record

### 6.1 Subscribing to many topics at once

- Message loss in the initial phase has been reported with 20 publishers at 1000 msg/sec
- rosbag2 uses a double-buffered producer-consumer model. If the consumer can't drain the queue, messages are lost

### 6.2 --max-cache-size

| Value | Suitable for |
|---|---|
| 1 MB (default) | Only lightweight topics (JointState, etc.) |
| 100-500 MB | Recordings that include images |
| 500 MB-1 GB | High bandwidth (PointCloud + many images) |

### 6.3 MCAP vs SQLite3 performance

| Aspect | MCAP | SQLite3 |
|---|---|---|
| Loss on bag splitting | **None** (append-only) | **Significant loss** (known issue) |
| Crash resilience | High (only the most recent chunk is damaged) | Low (the whole DB can be damaged) |
| Compression | Efficient (per chunk) | Inefficient (per message) |

Using `-s mcap` in this project is the right call.

### 6.4 Differences between DDS implementations

Results from high-rate (>1kHz) tests:

| DDS implementation | Message loss rate | Notes |
|---|---|---|
| **Cyclone DDS** | **0%** | |
| Fast DDS (eProsima) | 60-70% (Release build) | **Used in this project**; better in Debug build |
| RTI Connext | 21-45% | |

Cyclone DDS is the most stable in high-rate scenarios. Even so, ~20-message losses have been reported for very large messages (~5MB).

This project runs on Fast DDS, the ROS 2 Humble default, which fares worst in these >1kHz benchmarks. The topics recorded here are well below that rate, so the benchmark is not directly applicable — but switching implementations is a lever worth remembering if high-rate loss ever shows up.

### 6.5 The "cleanup after SIGINT" problem when launched via subprocess

When `ros2 bag record` receives SIGINT, it runs the following cleanup sequence:

1. The Python signal handler calls `rclcpp::shutdown()`
2. SubscriptionBase's destructor → DataReader is destroyed
3. **`Recorder::stop()`**: drains the internal message queue and flushes to the MCAP writer
4. MCAP writer destructor: closes out any remaining buffers
5. **Emits a large amount of cleanup logs to stderr**: `[rosbag2_storage]: Closed bag`, `[rosbag2_recorder]: Stopping recorder...`, etc.

If the process was **launched via subprocess** with stdout/stderr set to `subprocess.PIPE`, the following goes wrong:

- The PIPE buffer is around **64 KB** on Linux by default
- If nobody reads the PIPE during recording, it fills up over time
- Step (5) emits a large amount of logging → `write()` blocks → the flush inside `Recorder::stop()` is interrupted
- Eventually the MCAP writer's close is cut short, and **the last few frames / seconds are never flushed**
- When run directly in a terminal, stdout/stderr are TTYs and writes never block, so the cleanup sequence completes and frames are written all the way to the end

Symptom observed on the real robot: a 9.8s recording produces `end_early_sec` (based on `header.stamp`) of 0.66-1.86s (varies per camera). The robot's `/mcap/*` is not affected, suggesting the cause is not the MCAP writer itself but **the publisher-side backlog being truncated before flush**.

**Workaround in this project**: a pty is used to **bundle stdin/stdout/stderr into a single channel**, so from `ros2 bag record`'s perspective it sees a complete TTY environment. A drain thread continuously reads from the pty master to prevent the pty buffer from filling during cleanup. This eliminates the end-of-recording loss and produces the same behavior as a direct terminal launch. See `bag_record()` in [backend/app/infra/ros2/command.py](../../backend/app/infra/ros2/command.py) and `RecordProcess` in [backend/app/infra/ros2/record_process.py](../../backend/app/infra/ros2/record_process.py) for the implementation.

### 6.6 Clock skew between log_time and header.stamp

Each message in an MCAP file carries two timestamps:

| Timestamp | Set by | Use |
|---|---|---|
| **log_time** | `ros2 bag record` (recorder-side wall clock) | Key for the MCAP chunk index. Available via `reader.get_summary().statistics.message_start_time` |
| **header.stamp** | Publisher node (sensor/robot side) | Time the sensor sampled the data. Basis for quality analysis and timeline display |

These usually differ by only a few to a few tens of ms, but if the **robot's RTC is not NTP-synced**, the skew can be days or months. An example observed in real data:

| | Value (UTC) |
|---|---|
| Filename | `sample_task_20260401_055019` |
| log_time | 2026-04-01 05:50:20 - 05:51:10 (recorder wall clock) |
| header.stamp | 2026-01-30 19:14:41 - 19:15:31 (robot side) |
| Difference | **60.44 days (5,222,139 seconds)** |

All 9 topics (the robot's `/mcap/*` and RealSense's `/*_depth_cam/*`) had the same ~60-day offset, indicating the robot-side PC's system clock was about 60 days behind. Likely causes:

1. NTP not synchronized (check with `timedatectl set-ntp true`)
2. CMOS battery exhausted, so the RTC resets on every boot
3. A fixed time is used inside Docker / the container
4. Manual time setting on the robot controller side

**How the system handles it**:

- **Quality analysis / timeline display**: uses the **relative** value of `header.stamp` (seconds since recording start), so the absolute-time skew is ignored
- **Rug plot (Message Ticks)**: the MCAP chunk index is `log_time`-based, so a time range specified on `header.stamp` matches nothing. `TimelineData.log_time_offset_ns` (= `log_time_min - recording_start_ns`) is cached, and filter ranges are converted into log_time coordinates
- **File-listing timestamps**: based on `log_time`, so the recorder's correct time is displayed

To check or fix the time on the real robot:

```bash
# Run on the robot-side PC
date                                  # Check system time
timedatectl                           # Check NTP sync status
ros2 topic echo /mcap/body --once     # Check header.stamp.sec directly

# Enable NTP
sudo timedatectl set-ntp true
sudo systemctl status systemd-timesyncd
```

---

## 7. Tuning for data quality

### 7.1 Linux kernel parameters

```bash
# Enlarge UDP socket buffers (required)
sudo sysctl -w net.core.rmem_max=8388608       # Max receive buffer: 8MB
sudo sysctl -w net.core.wmem_max=8388608       # Max send buffer: 8MB
sudo sysctl -w net.core.rmem_default=2097152    # Default receive buffer: 2MB

# Shorten IP fragment reassembly timeout (important)
sudo sysctl -w net.ipv4.ipfrag_time=3           # 30s → 3s
sudo sysctl -w net.ipv4.ipfrag_high_thresh=134217728  # Fragment memory limit: 128MB

# Persist (/etc/sysctl.d/10-dds-tuning.conf)
net.core.rmem_max=8388608
net.core.wmem_max=8388608
net.core.rmem_default=2097152
net.ipv4.ipfrag_time=3
net.ipv4.ipfrag_high_thresh=134217728
```

### 7.2 DDS implementation configuration

Socket buffer sizes, transports, and discovery are configured through the DDS implementation's own XML file — the ROS 2 API has no way to express them. The syntax is implementation-specific and not interchangeable.

This project runs on Fast DDS, so the file is a Fast DDS profiles XML:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<dds xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <profiles>
    <transport_descriptors>
      <transport_descriptor>
        <transport_id>udp_large_buffers</transport_id>
        <type>UDPv4</type>
        <sendBufferSize>8388608</sendBufferSize>
        <receiveBufferSize>8388608</receiveBufferSize>
        <maxMessageSize>65500</maxMessageSize>
      </transport_descriptor>
    </transport_descriptors>

    <participant profile_name="tuned_participant" is_default_profile="true">
      <rtps>
        <userTransports>
          <transport_id>udp_large_buffers</transport_id>
        </userTransports>
        <!-- false replaces the builtin transports entirely, which also drops the
             default Shared Memory transport (see §3.5) -->
        <useBuiltinTransports>false</useBuiltinTransports>
      </rtps>
    </participant>
  </profiles>
</dds>
```

Point to it via an environment variable: `export FASTRTPS_DEFAULT_PROFILES_FILE=/path/to/fastdds.xml` (Humble ships Fast DDS 2.6, which still uses the `FASTRTPS_` prefix). Because the recording subprocess inherits the backend's environment (`app/infra/ros2/command.py`), setting it on the container covers both the rclpy monitor and `ros2 bag record`.

QoS written in this file is normally discarded: `rmw_fastrtps_cpp` overwrites it with the QoS coming from the ROS 2 API. `RMW_FASTRTPS_USE_QOS_FROM_XML=1` reverses that precedence, but it then competes with the per-topic reliability this project passes through `--qos-profile-overrides-path` (see §3.4), so the two should not be mixed casually.

**This repository ships no profiles XML** — the DDS layer runs on stock defaults. Add one only when a measured problem calls for it.

### 7.3 Real-time scheduling (for high-rate data)

```bash
# Real-time scheduling with SCHED_FIFO (priority 50)
chrt -f 50 ros2 bag record -s mcap ...

# CPU isolation (kernel parameter)
# Add to GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub
isolcpus=2,3

# Memory locking (/etc/security/limits.conf)
<username>    -   rtprio   98
<username>    -   memlock  -1
```

### 7.4 Recommended QoS

| Topic kind | Reliability | History depth | Reason |
|---|---|---|---|
| Images (high bandwidth) | BEST_EFFORT | 5 | Old frames are unneeded. Prefer low latency over loss avoidance |
| JointState (high rate) | RELIABLE | 100+ | Control-data loss heavily impacts learning |
| TF | RELIABLE | 100 | Frame-transform consistency |

### 7.5 Notes on Docker environments

```yaml
# docker-compose.yml
services:
  recorder:
    network_mode: host    # Required for DDS multicast discovery
    ipc: host             # Needed if you use Shared Memory Transport
```

---

## 8. Top 10 reasons DDS messages get dropped

From the RTI official blog "The Top 10 Reasons for Dropped DDS Messages":

| # | Cause | Details |
|---|---|---|
| 1 | **Best Effort communication** | No retransmit. Lost or out-of-order messages can't be recovered |
| 2 | **KEEP_LAST setting** | Writer/reader queue overflows overwrite old messages |
| 3 | **Time-based / content filters** | Messages outside the filter are intentionally discarded |
| 4 | **No Durability set (Volatile)** | Initial messages lost depending on startup order |
| 5 | **Insufficient write queue space** | Hitting `max_blocking_time` causes unrecoverable loss |
| 6 | **Listener blocking** | Long-running callbacks overflow socket buffers |
| 7 | **Heartbeat retry limit** | Reader is declared inactive after `max_heartbeat_retries` |
| 8 | **Sequence/string max length exceeded** | DataReader discards |
| 9 | **Value restrictions via IDL annotations** | Out-of-range data is discarded |
| 10 | **destination_order QoS** | Data with an older source timestamp is discarded |

---

## 9. References

### Official documentation

- [ROS2: Quality of Service Settings](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html)
- [ROS2: DDS Tuning Information](https://docs.ros.org/en/humble/How-To-Guides/DDS-tuning.html)
- [ROS2: QoS Deadline, Liveliness, and Lifespan](https://design.ros2.org/articles/qos_deadline_liveliness_lifespan.html)
- [ROS2: Overriding QoS Policies for Recording](https://docs.ros.org/en/humble/How-To-Guides/Overriding-QoS-Policies-For-Recording-And-Playback.html)

### DDS implementations

- [Fast DDS: Standard QoS Policies](https://fast-dds.docs.eprosima.com/en/latest/fastdds/dds_layer/core/policy/standardQosPolicies.html)
- [Fast DDS: Shared Memory Transport](https://fast-dds.docs.eprosima.com/en/latest/fastdds/transport/shared_memory/shared_memory.html)
- [Fast DDS: XML Profiles](https://fast-dds.docs.eprosima.com/en/v2.6.0/fastdds/xml_configuration/xml_configuration.html)
- [Eclipse Cyclone DDS: Configuration](https://cyclonedds.io/docs/cyclonedds/latest/config/index.html)
- [RTI: Top 10 Reasons for Dropped DDS Messages](https://www.rti.com/blog/top-10-reasons-for-dropped-dds-messages)
- [RTI: Reliable Protocol Overview](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/users_manual/users_manual/Overview_of_the_Reliable_Protocol.htm)

### Specifications

- [OMG DDSI-RTPS 2.3 Specification](https://www.omg.org/spec/DDSI-RTPS/2.3/)
- [OMG DDS Foundation: Reliability QoS](https://www.omgwiki.org/ddsf/doku.php?id=ddsf:public:guidebook:06_append:02_quality_of_service:reliability)

### Known issues

- [rosbag2 #967: QoS Discovery Race Condition](https://github.com/ros2/rosbag2/issues/967)
- [rosbag2 #1579: Cache Buffer Dropping Messages](https://github.com/ros2/rosbag2/issues/1579)
- [rmw_fastrtps #338: Message Drops in High Frequency](https://github.com/ros2/rmw_fastrtps/issues/338)
