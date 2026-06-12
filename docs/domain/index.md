# Domain Knowledge Guide

> Explains the background knowledge developers without a robotics background need to understand this project.

## Where this project fits

OpenLUTRA is a tool for recording **teaching data** (demonstration motions) from a robot. The recorded MCAP files are processed into imitation-learning data for AI by a separate conversion/annotation pipeline.

```
[Physical robot] ──ROS2──▶ [OpenLUTRA (this repo)] ──┬──▶ [MCAP file]
                                                     │
                                                     └──▶ [Upload destination]
                                                          (S3-compatible today;
                                                           GCS / local-network
                                                           on the roadmap)
                                                          │
                                                          ▼
                                            External conversion/annotation
                                            pipeline (LeRobot, etc.)
```

This repository's scope covers **MCAP recording, quality verification, and shipping the resulting archive to a configured upload destination**. Downstream conversion / annotation remains out of scope.

## Domain knowledge

| Document | Contents |
|---|---|
| [DDS communication and gaps](dds_gap.md) | Why messages get lost over DDS, how it relates to QoS, and how to tune it |
| [Quality analysis](quality_analysis.md) | Metrics, score calculation, status determination |
| [Custom validators](custom_validators.md) | How the per-recording auto-validation works, and how to add your own rules |
| [Upload to a destination](upload.md) | Lifecycle, the destination abstraction, key-template syntax, and failure modes |
| [SSE stream](sse.md) | Spec for real-time data delivery (event list, connection example) |
