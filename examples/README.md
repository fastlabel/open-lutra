# Examples

Usage examples and reference implementations for OpenLUTRA.

## License

Code under this directory is licensed under the **BSD Zero Clause License (0BSD)** (different from the Apache License 2.0 used at the repository root). See [LICENSE](./LICENSE) for details.

0BSD is effectively public-domain-equivalent: you may use, copy, modify, and redistribute the code freely, with no attribution requirement. You may incorporate sample code into your own projects as-is.

## Positioning

- Code under this directory is **reference material**, not part of OpenLUTRA's official feature surface.
- There is no API compatibility guarantee — changes in the main project may break these examples.
- Bug reports and improvement issues are welcome, but support priority is lower than for the main project.

## Relation to the project root (Apache 2.0)

If you want to use the project root's `/app` etc. under 0BSD, copy the relevant files into this directory and use them from there. Code outside this directory must be used under the Apache 2.0 terms (attribution, retention of `NOTICE`, etc.).

## Available examples

| Example | Description |
|---|---|
| [`custom_ros2_messages/`](./custom_ros2_messages/) | How to record topics that use custom ROS2 message types (vendor-specific or user-defined), including a sample `Dockerfile`. |
| [`greengrass/`](./greengrass/) | Deploying OpenLUTRA to edge PCs with AWS IoT Greengrass V2 and monitoring them from a local web console (Fleet Console). |
