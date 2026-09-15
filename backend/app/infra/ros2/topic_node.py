"""ROS2 topic monitor node (infrastructure layer).

Handles topic discovery, subscription, and automatic QoS matching on the DDS
domain. Contains no domain logic and delegates to the service layer via
callbacks.
"""

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from rclpy.subscription import Subscription  # noqa: TC002 (regular import; not used to avoid a circular import)

from app.infra.ros2.message import import_message_class, msg_to_dict

logger = logging.getLogger(__name__)


class TopicMonitorNode(Node):  # type: ignore[misc]
    """Infrastructure layer that discovers and subscribes to topics as an rclpy Node.

    Structurally implements the TopicSubscriber Protocol. The domain service
    (TopicMonitorService) references this node via the protocol, avoiding any
    direct dependency on rclpy.
    """

    def __init__(self, *, qos_depth: int = 30) -> None:
        super().__init__("topic_monitor")
        self._sub_map: dict[str, Subscription] = {}
        self._qos_depth = qos_depth

    def discover_topics(self) -> list[tuple[str, list[str]]]:
        result: list[tuple[str, list[str]]] = self.get_topic_names_and_types()
        return result

    def subscribe_topic(
        self,
        topic_name: str,
        msg_type_str: str,
        callback: Callable[[str, Any], None],
    ) -> str | None:
        """Subscribe to a topic.

        Args:
            topic_name: Topic name.
            msg_type_str: Message type string (e.g., "sensor_msgs/msg/JointState").
            callback: Callback receiving (topic_name, msg).

        Returns:
            The QoS reliability string ("RELIABLE" or "BEST_EFFORT"), or
            None if importing the message type failed.
        """
        msg_class = import_message_class(msg_type_str)
        if msg_class is None:
            return None

        # Fetch the publisher's QoS and auto-match against it
        reliability = QoSReliabilityPolicy.BEST_EFFORT
        durability = QoSDurabilityPolicy.VOLATILE
        try:
            pub_info = self.get_publishers_info_by_topic(topic_name)
            if pub_info:
                pub_qos = pub_info[0].qos_profile
                reliability = pub_qos.reliability
                durability = pub_qos.durability
        except Exception:
            logger.warning("Failed to fetch QoS: %s (falling back to BEST_EFFORT)", topic_name)

        qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=self._qos_depth,
            reliability=reliability,
            durability=durability,
        )
        sub = self.create_subscription(
            msg_class,
            topic_name,
            partial(callback, topic_name),
            qos,
        )
        self._sub_map[topic_name] = sub

        rel_str = "RELIABLE" if reliability == QoSReliabilityPolicy.RELIABLE else "BEST_EFFORT"
        logger.debug("Subscribed to %s (QoS: %s)", topic_name, rel_str)
        return rel_str

    def unsubscribe_topic(self, topic_name: str) -> None:
        sub = self._sub_map.pop(topic_name, None)
        if sub is not None:
            self.destroy_subscription(sub)

    def convert_message(self, msg: Any) -> dict[str, Any]:
        return msg_to_dict(msg)
