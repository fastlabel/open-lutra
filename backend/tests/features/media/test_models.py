"""Tests for media feature domain models (topic classification for the FL format)."""

import pytest

from app.features.media.models import (
    JointStateMapping,
    JointTopicEntry,
    TopicRole,
    build_joint_state_mapping,
    classify_joint_state_topic,
    derive_camera_name,
    derive_joint_prefix,
)


class TestClassifyJointStateTopic:
    """Tests for classifying the role of a JointState topic."""

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("/robot_slave/states", TopicRole.OBSERVATION),
            ("/arm/status", TopicRole.OBSERVATION),
            ("/controller/feedback", TopicRole.OBSERVATION),
        ],
    )
    def test_observation_keywords(self, topic: str, expected: TopicRole) -> None:
        assert classify_joint_state_topic(topic) == expected

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("/robot_master/cmd", TopicRole.ACTION),
            ("/arm/command", TopicRole.ACTION),
            ("/controller/target", TopicRole.ACTION),
            ("/teleop/goal", TopicRole.ACTION),
        ],
    )
    def test_action_keywords(self, topic: str, expected: TopicRole) -> None:
        assert classify_joint_state_topic(topic) == expected

    def test_unclassifiable(self) -> None:
        assert classify_joint_state_topic("/robot/joint_data") is None

    def test_empty_topic(self) -> None:
        assert classify_joint_state_topic("") is None

    def test_action_takes_priority_over_observation(self) -> None:
        """Tokens are scanned in order; the first match wins."""
        result = classify_joint_state_topic("/cmd/states")
        assert result == TopicRole.ACTION

    def test_master_token_before_state(self) -> None:
        """When split on '_', "master" appears before "state" -> ACTION."""
        result = classify_joint_state_topic("/robot_master/state")
        assert result == TopicRole.ACTION

    def test_exact_segment_match(self) -> None:
        """Keywords match tokens exactly (no substring matching)."""
        assert classify_joint_state_topic("/robot/commanding") is None
        assert classify_joint_state_topic("/robot/feedbacks") is None

    # --- Keywords: slave / master / body ---

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("/mcap/slave_arm_right", TopicRole.OBSERVATION),
            ("/mcap/slave_arm_left", TopicRole.OBSERVATION),
            ("/mcap/body", TopicRole.OBSERVATION),
        ],
    )
    def test_slave_and_body_classified_as_observation(self, topic: str, expected: TopicRole) -> None:
        assert classify_joint_state_topic(topic) == expected

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("/mcap/master_arm_right", TopicRole.ACTION),
            ("/mcap/master_arm_left", TopicRole.ACTION),
        ],
    )
    def test_master_classified_as_action(self, topic: str, expected: TopicRole) -> None:
        assert classify_joint_state_topic(topic) == expected

    def test_underscore_splitting(self) -> None:
        """Topic names are tokenized on both '/' and '_'."""
        # "slave_arm_right" -> ["slave", "arm", "right"]
        assert classify_joint_state_topic("/mcap/slave_arm_right") == TopicRole.OBSERVATION


class TestDeriveCameraName:
    """Tests for deriving a camera name."""

    @pytest.mark.parametrize(
        ("topic", "expected"),
        [
            ("/right_arm_depth_cam/color/image_raw/compressed", "right_arm_depth_cam"),
            ("/some_cam/camera/color/image_raw/compressed", "some_cam"),
            ("/left_arm_depth_cam/color/image_raw/compressed", "left_arm_depth_cam"),
        ],
    )
    def test_derives_first_segment(self, topic: str, expected: str) -> None:
        assert derive_camera_name(topic) == expected

    def test_single_segment(self) -> None:
        assert derive_camera_name("/camera") == "camera"

    def test_no_leading_slash(self) -> None:
        assert derive_camera_name("camera/image") == "camera"

    def test_empty_string(self) -> None:
        assert derive_camera_name("") == ""


class TestDeriveJointPrefix:
    """Tests for deriving the joint-name prefix."""

    def test_right_arm(self) -> None:
        assert derive_joint_prefix("/mcap/slave_arm_right") == "R_"

    def test_left_arm(self) -> None:
        assert derive_joint_prefix("/mcap/slave_arm_left") == "L_"

    def test_body(self) -> None:
        assert derive_joint_prefix("/mcap/body") == ""

    def test_no_side_indicator(self) -> None:
        assert derive_joint_prefix("/robot/joint_data") == ""


class TestBuildJointStateMapping:
    """Tests for building the JointState mapping."""

    def test_both_obs_and_action(self) -> None:
        """Case with both observation and action."""
        topics = {
            "/robot_slave/states": "sensor_msgs/msg/JointState",
            "/robot_master/cmd": "sensor_msgs/msg/JointState",
        }
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == ["/robot_slave/states"]
        assert mapping.action_topics == ["/robot_master/cmd"]

    def test_observation_only(self) -> None:
        """When only observation is present, action reuses observation."""
        topics = {"/robot_slave/states": "sensor_msgs/msg/JointState"}
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == ["/robot_slave/states"]
        assert mapping.action_topics == ["/robot_slave/states"]

    def test_action_only(self) -> None:
        """When only action is present, observation reuses action."""
        topics = {"/robot_master/cmd": "sensor_msgs/msg/JointState"}
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == ["/robot_master/cmd"]
        assert mapping.action_topics == ["/robot_master/cmd"]

    def test_unclassifiable_single(self) -> None:
        """A lone unclassifiable topic is used as observation."""
        topics = {"/robot/joint_data": "sensor_msgs/msg/JointState"}
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == ["/robot/joint_data"]

    def test_obs_plus_unclassifiable(self) -> None:
        """observation + unclassifiable -> the unclassifiable one is assigned to action."""
        topics = {
            "/robot_slave/states": "sensor_msgs/msg/JointState",
            "/robot/joint_data": "sensor_msgs/msg/JointState",
        }
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == ["/robot_slave/states"]
        assert mapping.action_topics == ["/robot/joint_data"]

    def test_action_plus_unclassifiable(self) -> None:
        """action + unclassifiable -> the unclassifiable one is assigned to observation."""
        topics = {
            "/robot_master/cmd": "sensor_msgs/msg/JointState",
            "/robot/joint_data": "sensor_msgs/msg/JointState",
        }
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == ["/robot/joint_data"]
        assert mapping.action_topics == ["/robot_master/cmd"]

    def test_empty_dict(self) -> None:
        assert build_joint_state_mapping({}) is None

    # --- Support for multiple topics ---

    def test_custom_full_topics(self) -> None:
        """Full set of custom-typed topics: both-arm slave/master + body."""
        topics = {
            "/mcap/slave_arm_right": "custom_msgs/msg/ArmSlaveData",
            "/mcap/slave_arm_left": "custom_msgs/msg/ArmSlaveData",
            "/mcap/master_arm_right": "custom_msgs/msg/ArmMasterData",
            "/mcap/master_arm_left": "custom_msgs/msg/ArmMasterData",
            "/mcap/body": "custom_msgs/msg/BodyData",
        }
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == [
            "/mcap/slave_arm_right",
            "/mcap/slave_arm_left",
            "/mcap/body",
        ]
        assert mapping.action_topics == [
            "/mcap/master_arm_right",
            "/mcap/master_arm_left",
        ]

    def test_joint_prefix_in_entries(self) -> None:
        """Each entry is given a URDF prefix."""
        topics = {
            "/mcap/body": "custom_msgs/msg/BodyData",
            "/mcap/slave_arm_right": "custom_msgs/msg/ArmSlaveData",
            "/mcap/slave_arm_left": "custom_msgs/msg/ArmSlaveData",
        }
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        prefixes = [e.joint_prefix for e in mapping.observation_entries]
        assert prefixes == ["R_", "L_", ""]

    def test_stable_ordering_after_remove_and_readd(self) -> None:
        """Order is unchanged after removing and re-adding topics."""
        all_topics = {
            "/mcap/body": "BodyData",
            "/mcap/slave_arm_right": "ArmSlaveData",
            "/mcap/slave_arm_left": "ArmSlaveData",
        }
        mapping_full = build_joint_state_mapping(all_topics)

        without_right = {k: v for k, v in all_topics.items() if "right" not in k}
        mapping_partial = build_joint_state_mapping(without_right)
        assert mapping_partial is not None
        assert mapping_partial.observation_topics == ["/mcap/slave_arm_left", "/mcap/body"]

        mapping_readd = build_joint_state_mapping(all_topics)
        assert mapping_readd is not None
        assert mapping_readd.observation_topics == mapping_full.observation_topics

    def test_multiple_obs_and_action_sorted(self) -> None:
        """Multiple obs/action topics are each sorted stably."""
        topics = {
            "/mcap/slave_arm_left": "ArmSlaveData",
            "/mcap/master_arm_left": "ArmMasterData",
            "/mcap/slave_arm_right": "ArmSlaveData",
            "/mcap/master_arm_right": "ArmMasterData",
        }
        mapping = build_joint_state_mapping(topics)
        assert mapping is not None
        assert mapping.observation_topics == [
            "/mcap/slave_arm_right",
            "/mcap/slave_arm_left",
        ]
        assert mapping.action_topics == [
            "/mcap/master_arm_right",
            "/mcap/master_arm_left",
        ]


class TestJointStateMapping:
    """Behavior tests for JointStateMapping."""

    def test_observation_topics_property(self) -> None:
        mapping = JointStateMapping(
            observation_entries=(
                JointTopicEntry(topic="/body", joint_prefix=""),
                JointTopicEntry(topic="/right", joint_prefix="R_"),
            ),
            action_entries=(),
        )
        assert mapping.observation_topics == ["/body", "/right"]

    def test_action_topics_property(self) -> None:
        mapping = JointStateMapping(
            observation_entries=(JointTopicEntry(topic="/states", joint_prefix=""),),
            action_entries=(JointTopicEntry(topic="/cmd", joint_prefix=""),),
        )
        assert mapping.action_topics == ["/cmd"]

    def test_empty_action(self) -> None:
        mapping = JointStateMapping(
            observation_entries=(JointTopicEntry(topic="/states", joint_prefix=""),),
            action_entries=(),
        )
        assert mapping.action_topics == []
