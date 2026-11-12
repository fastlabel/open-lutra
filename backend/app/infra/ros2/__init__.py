"""ROS2 infrastructure (CLI execution, message conversion, topic monitor node, thread management).

Public API:
    ROS2Command / ROS2CommandError: ROS2 CLI wrapper
    RecordProcess: Control over a recording process started with --start-paused
    QoSOverrideFile: Temporary file management for QoS override YAML
    describe_exit: Human-readable exit status of the recording process

Note: TopicMonitorThread / TopicMonitorNode depend on rclpy and are not
included in the barrel. Import them directly from their call sites (main.py).
"""

from app.infra.ros2.command import ROS2Command, ROS2CommandError
from app.infra.ros2.qos import QoSOverrideFile
from app.infra.ros2.record_log import describe_exit
from app.infra.ros2.record_process import RecordProcess

__all__ = [
    "QoSOverrideFile",
    "ROS2Command",
    "ROS2CommandError",
    "RecordProcess",
    "describe_exit",
]
