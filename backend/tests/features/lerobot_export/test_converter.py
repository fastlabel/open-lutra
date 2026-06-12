"""Tests for the pure conversion pipeline (alignment / resampling / framing)."""

import pytest

from app.features.lerobot_export import converter
from app.features.lerobot_export.models import ExportConfig, SourceConfig

from ._fakes import image_message, joint_message

MS = 1_000_000  # nanoseconds per millisecond


def _config(**overrides: object) -> ExportConfig:
    base: dict = {
        "images": {"cam": "/img"},
        "observation": {"state": [SourceConfig(topic="/state", field="position", type="list", indices=[0])]},
        "action": [SourceConfig(topic="/cmd", field="position", type="list", indices=[0])],
        "sync_tolerance_ms": 1000.0,
        "image_tolerance_ms": 1000.0,
    }
    base.update(overrides)
    return ExportConfig(**base)  # type: ignore[arg-type]


def test_detect_fps_from_image_topic() -> None:
    messages = {"/img": [image_message(0), image_message(100 * MS), image_message(200 * MS)]}
    assert converter.detect_fps(messages, ["/img"]) == 10


def test_detect_fps_fallback_when_no_images() -> None:
    assert converter.detect_fps({"/img": [image_message(0)]}, ["/img"]) == 30
    assert converter.detect_fps({}, ["/img"]) == 30


def test_compute_ref_timestamps_empty() -> None:
    assert converter.compute_ref_timestamps({}, 10, "intersection") == []


def test_compute_ref_timestamps_intersection() -> None:
    messages = {
        "/a": [joint_message(0, [0.0]), joint_message(1000 * MS, [0.0])],
        "/b": [joint_message(200 * MS, [0.0]), joint_message(800 * MS, [0.0])],
    }
    out = converter.compute_ref_timestamps(messages, 10, "intersection")
    assert out[0] == 200 * MS and out[-1] <= 800 * MS


def test_compute_ref_timestamps_union() -> None:
    messages = {
        "/a": [joint_message(0, [0.0]), joint_message(500 * MS, [0.0])],
        "/b": [joint_message(200 * MS, [0.0]), joint_message(900 * MS, [0.0])],
    }
    out = converter.compute_ref_timestamps(messages, 10, "union")
    assert out[0] == 0 and out[-1] <= 900 * MS


def test_compute_ref_timestamps_no_overlap() -> None:
    messages = {
        "/a": [joint_message(0, [0.0]), joint_message(100 * MS, [0.0])],
        "/b": [joint_message(500 * MS, [0.0]), joint_message(600 * MS, [0.0])],
    }
    assert converter.compute_ref_timestamps(messages, 10, "intersection") == []


def test_probe_feature_spec() -> None:
    config = _config(
        observation={
            "state": [
                SourceConfig(topic="/state", field="position", type="list", indices=[0, 1], names=["a", "b"]),
            ]
        },
        action=[SourceConfig(topic="/cmd", field="position", type="list", indices=[0, 1])],
    )
    messages = {
        "/img": [image_message(0, size=4)],
        "/state": [joint_message(0, [1.0, 2.0])],
        "/cmd": [joint_message(0, [3.0, 4.0])],
    }
    spec = converter.probe_feature_spec(messages, config)
    assert spec.camera_names == ["cam"]
    assert spec.image_shapes["cam"] == (4, 4, 3)
    assert spec.observation_fields["state"] == (2, ["a", "b"])
    assert spec.action_dim == 2
    assert spec.action_names == ["action_0", "action_1"]  # auto names


def test_probe_feature_spec_missing_image_topic() -> None:
    with pytest.raises(ValueError, match="image topic"):
        converter.probe_feature_spec({"/state": [joint_message(0, [1.0])]}, _config())


def test_probe_feature_spec_missing_source_topic() -> None:
    messages = {"/img": [image_message(0)], "/cmd": [joint_message(0, [1.0])]}
    with pytest.raises(ValueError, match="No messages for topic: /state"):
        converter.probe_feature_spec(messages, _config())


def test_align_nearest_forward_fill_empty() -> None:
    assert converter.align_nearest_forward_fill([0, 1], [], 10) == [None, None]


def test_align_nearest_within_tolerance() -> None:
    messages = [image_message(0), image_message(100 * MS)]
    aligned = converter.align_nearest_forward_fill([10 * MS, 90 * MS], messages, tolerance_ns=30 * MS)
    assert aligned[0] is messages[0]  # nearest to t=0
    assert aligned[1] is messages[1]  # nearest to t=100ms


def test_align_forward_fills_last_match() -> None:
    messages = [image_message(0)]  # only one message
    aligned = converter.align_nearest_forward_fill([0, 50 * MS, 1000 * MS], messages, tolerance_ns=10 * MS)
    assert aligned == [messages[0], messages[0], messages[0]]  # held forward past tolerance


def test_align_forward_fill_none_before_first_match() -> None:
    messages = [image_message(1000 * MS)]
    aligned = converter.align_nearest_forward_fill([0], messages, tolerance_ns=1)
    assert aligned == [None]


def test_iter_episode_frames_empty_timebase() -> None:
    assert list(converter.iter_episode_frames({}, _config(), [], "t")) == []


def test_iter_episode_frames_full() -> None:
    config = _config()
    ref = [0, 100 * MS]
    messages = {
        "/img": [image_message(0), image_message(100 * MS)],
        "/state": [joint_message(0, [1.0]), joint_message(100 * MS, [2.0])],
        "/cmd": [joint_message(0, [9.0]), joint_message(100 * MS, [8.0])],
    }
    frames = list(converter.iter_episode_frames(messages, config, ref, "pick"))
    assert len(frames) == 2
    assert frames[0].task == "pick"
    assert frames[0].camera_images["cam"].shape == (2, 2, 3)
    assert frames[0].observations["state"].tolist() == [1.0]
    assert frames[0].action.tolist() == [9.0]


def test_iter_episode_frames_drops_when_image_missing() -> None:
    config = _config()
    ref = [0]
    messages = {
        "/img": [],  # no image -> frame dropped
        "/state": [joint_message(0, [1.0])],
        "/cmd": [joint_message(0, [9.0])],
    }
    assert list(converter.iter_episode_frames(messages, config, ref, "t")) == []


def test_iter_episode_frames_drops_when_source_missing() -> None:
    config = _config()
    ref = [0]
    messages = {
        "/img": [image_message(0)],
        "/state": [],  # observation missing -> dropped
        "/cmd": [joint_message(0, [9.0])],
    }
    assert list(converter.iter_episode_frames(messages, config, ref, "t")) == []


def test_iter_episode_frames_multi_source_concat() -> None:
    config = _config(
        observation={
            "state": [
                SourceConfig(topic="/state", field="position", type="list", indices=[0, 1]),
                SourceConfig(topic="/cmd", field="position", type="list", indices=[0]),
            ]
        },
    )
    ref = [0]
    messages = {
        "/img": [image_message(0)],
        "/state": [joint_message(0, [1.0, 2.0])],
        "/cmd": [joint_message(0, [3.0])],
    }
    frames = list(converter.iter_episode_frames(messages, config, ref, "t"))
    assert frames[0].observations["state"].tolist() == [1.0, 2.0, 3.0]


def test_iter_episode_frames_empty_action_drops() -> None:
    config = _config(action=[])
    ref = [0]
    messages = {"/img": [image_message(0)], "/state": [joint_message(0, [1.0])]}
    assert list(converter.iter_episode_frames(messages, config, ref, "t")) == []


def test_iter_episode_frames_drops_when_action_source_missing() -> None:
    config = _config()
    ref = [0]
    messages = {
        "/img": [image_message(0)],
        "/state": [joint_message(0, [1.0])],
        "/cmd": [],  # action source has no messages -> value None -> dropped
    }
    assert list(converter.iter_episode_frames(messages, config, ref, "t")) == []
