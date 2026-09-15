"""Simulator configuration (read from environment variables).

SIM_MODE:
  normal       — Stable publishing (default)
  unstable     — Jitter + random drops on some topics
  topic_stop   — Stop publishing the specified topic after N seconds
  camera_empty — Keep publishing camera topics but make some frames empty (0 bytes)
  burst        — Periodic gap + DDS-burst-style consecutive sends
  mixed        — unstable + topic_stop + camera_empty combined (closest to real hardware)
"""

import os

# --- Simulation mode ---
SIM_MODE = os.environ.get("SIM_MODE", "normal")

# --- unstable ---
# Drop rate (0.0-1.0)
DROP_RATE = float(os.environ.get("SIM_DROP_RATE", "0.1"))
# Jitter/drop target topics ("all" for every topic)
_UNSTABLE_TOPICS_RAW = os.environ.get("SIM_UNSTABLE_TOPICS", "all")
UNSTABLE_TOPICS_ALL = _UNSTABLE_TOPICS_RAW.strip().lower() == "all"
UNSTABLE_TOPICS = [] if UNSTABLE_TOPICS_ALL else _UNSTABLE_TOPICS_RAW.split(",")

# --- topic_stop ---
# Seconds before publishing stops
STOP_AFTER_SEC = float(os.environ.get("SIM_STOP_AFTER_SEC", "15"))
# Topics to stop
STOP_TOPICS = os.environ.get("SIM_STOP_TOPICS", "/sim/slave_arm_left,/sim/master_arm_left").split(",")

# --- camera_empty ---
# Camera indices that should emit empty frames (0-based)
EMPTY_CAMERA_INDICES = [int(x) for x in os.environ.get("SIM_EMPTY_CAMERA_INDICES", "0").split(",")]
# Empty-frame rate (0.0-1.0)
EMPTY_FRAME_RATE = float(os.environ.get("SIM_EMPTY_FRAME_RATE", "0.3"))

# --- mixed: recovery cycle ---
# Duration of temporary recovery after stop (seconds)
MIXED_RECOVERY_SEC = float(os.environ.get("SIM_MIXED_RECOVERY_SEC", "10"))
# Duration before stopping again after recovery (seconds)
MIXED_RESTOP_SEC = float(os.environ.get("SIM_MIXED_RESTOP_SEC", "8"))

# --- burst ---
# Burst interval (seconds)
BURST_INTERVAL_SEC = float(os.environ.get("SIM_BURST_INTERVAL_SEC", "10"))
# Gap length (seconds)
BURST_GAP_SEC = float(os.environ.get("SIM_BURST_GAP_SEC", "2.0"))
# Number of messages sent in a single burst
BURST_COUNT = int(os.environ.get("SIM_BURST_COUNT", "50"))
