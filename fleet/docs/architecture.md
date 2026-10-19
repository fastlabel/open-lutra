# Architecture

How OpenLUTRA images get from the build environment to edge PCs via AWS IoT Greengrass V2.

## Overall flow

```
[Build environment / CI] ──docker push──▶ ECR (backend, frontend)
     │
     └─ create-component-version ─▶ Greengrass component
     │                               └─ OpenLutra (recipe + compose.yml, fastdds.xml on S3)
     └─ create-deployment (to a Thing Group)
                                          ▼
[Edge PC] Greengrass nucleus ──X.509 certificate──▶ AWS IoT Core
     │   └─ Token Exchange Service: certificate → temporary IAM credentials (via Role Alias)
     ├─ Fetch artifacts from S3
     ├─ DockerApplicationManager: pull images from ECR
     └─ Recipe lifecycle: docker compose up
```

Devices hold no long-lived AWS access keys. They authenticate to IoT Core with a certificate, and exchange it for temporary credentials of an IAM role only when accessing S3 or ECR. Registration (creating the Thing and certificate) is also done on the operator's PC, so devices never touch AWS credentials.

The backend image is built from the repository's root `Dockerfile`. The frontend image is built from `frontend/` with `docker/frontend.Dockerfile` (build context: the repository root, filtered by `docker/frontend.Dockerfile.dockerignore`).

## What is managed where

| Layer | Tool | Reason |
|---|---|---|
| Infrastructure: ECR, S3, IAM role, Role Alias, IoT Policy, operator group | Terraform (`infra/`) | Rarely changes once created |
| Thing Group | Fleet Console (`console/`) | Created each time a site is added |
| Release: component versions, deployments | AWS CLI (scripts / CI) | Component versions are immutable artifacts that accumulate with every release, so they do not belong in Terraform state. The aws provider also has no Greengrass V2 resources |
| Device registration: Thing, certificate, adding to a Thing Group | Script run on the operator's PC (`device/provision.sh`) | Finishes the work that needs AWS permissions outside the device |
| Device setup: Docker, Java, nucleus | Script run on the edge PC (`device/setup.sh`) | Work that runs on the edge PC itself. Uses no AWS credentials |

## Infrastructure resources (`infra/`)

### ECR repositories — `ecr.tf`

One repository per image (`open-lutra-backend`, `open-lutra-frontend`).

- **Tags cannot be overwritten (IMMUTABLE).** Pushing an existing tag fails. The backend and frontend get the same `IMAGE_TAG` (`git describe --tags` of the last commit that changed what goes into the images; see the [README](../README.md#release)), and the recipe points to both images by this tag. This guarantees that a released component version always points to the same backend / frontend pair.
- **Scan on push.** Every pushed image gets a basic vulnerability scan.

### Artifact bucket — `s3.tf`

Holds component artifacts other than container images (`compose.yml` and `fastdds.xml`). Keys are `<component name>/<version>/<file name>`, and artifacts of a released version are never overwritten. The recipe references them as `s3://<bucket>/<key>`, and the nucleus downloads them with the Token Exchange Role's permissions. The bucket is fully private.

### Token Exchange Role — `iam.tf`

The IAM role devices receive as temporary credentials.

- **Trust policy:** Only `credentials.iot.amazonaws.com` (the IoT credentials provider) can assume it. Users and other services cannot use this role.
- **Permissions:** The minimum needed to fetch a release.
  - `ecr:GetAuthorizationToken` — gets the token for `docker login` (by design it cannot be scoped to a repository)
  - `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` — pull. Limited to the two repositories
  - `s3:GetBucketLocation` — the nucleus looks up the bucket's region before fetching artifacts. Limited to the artifact bucket
  - `s3:GetObject` — downloads artifacts. Limited to the artifact bucket
  - `cloudwatch:PutMetricData` — the Status component sends metrics. Limited to the `OpenLUTRA` namespace
  - `logs:CreateLogGroup` and others — LogManager sends logs. Limited to log groups under `/aws/greengrass/`

When a component needs additional permissions (such as uploading recording data to S3), add them here.

### Operator group — `operator.tf`

An IAM group with only the permissions needed for releases, deployments, device registration, and Fleet Console. People who use an IAM user's access keys in `.env` are put in this group. ECR and the artifact bucket are limited to this infrastructure's, and `iot:AttachPolicy` to the core device IoT Policy. Greengrass, and the IoT job and shadow operations that deployments use internally, are `*` because the target ARNs cannot be determined in advance. IAM users and access keys are not created by Terraform (the keys would remain in the state).

### Role Alias — `iot.tf`

An IoT-side alias pointing to the Token Exchange Role. Devices are configured with this alias rather than the role's ARN, so the role can be swapped without changing device configuration. Greengrass's `TokenExchangeService` component calls the credentials provider with this alias.

### Core device IoT Policy — `iot.tf`

The policy attached to each device's certificate, defining what the device may do in IoT Core. Every resource is narrowed by the policy variable `${iot:Connection.Thing.ThingName}`, so even with one policy shared by all devices, each device can touch only its own topics.

| Statement | Purpose |
|---|---|
| `iot:Connect` to `client/<thing>*` | Connect over MQTT. The trailing `*` allows the additional connections the nucleus opens with a suffix on the client ID |
| `iot:Publish` / `iot:Receive` / `iot:Subscribe` to `$aws/things/<thing>*/*` | Deployments arrive via IoT Jobs and status is reported via the shadow. Both use topics under this prefix |
| `iot:AssumeRoleWithCertificate` to the Role Alias | Allows the certificate-to-IAM-credentials exchange described above |
| `greengrass:ResolveComponentCandidates`, `GetComponentVersionArtifact`, `GetDeploymentConfiguration`, `ListThingGroupsForCoreDevice` | APIs the nucleus calls to resolve and download a deployment's contents |

### Thing Group

Deployments target Thing Groups, not individual devices. When a device is added to a group, the group's current deployment is delivered automatically. The fleet is managed through this mechanism. Splitting groups per site or per stage lets each group run a different component version or config.

Thing Groups are not created by Terraform but from Fleet Console (`console/`). Like releases and deployments, they grow through operations, so they are not managed in Terraform state.

Put each device in only one of the groups that deploy OpenLutra. If several groups specify different versions of the same component, the device cannot resolve the version and the deployment fails.

## Components (`greengrass/`)

### Versions

- **`COMPONENT_VERSION` is independent of `IMAGE_TAG`.** A release that changes only the recipe also gets a new version (recording configs are sent by deployments, so they need no version). Which images to use is written into the recipe and cannot be overridden by a deployment. If it could, the images the nucleus pulls and the images compose starts would diverge.
- **Use only `MAJOR.MINOR.PATCH`.** The cloud accepts pre-release versions such as `0.4.3-7-gabc`, but the nucleus interprets the hyphen as an npm version range (`0.4.3 - 7-gabc`), so the device cannot resolve the version.

### OpenLutra

Runs `docker compose up` in the foreground. The nucleus watches this process and restarts it if it dies.

The recording config is sent with its contents in the deployment's component configuration (the file name in `RecordingConfigFile`, the YAML in `RecordingConfig`). At startup, the contents are written under the same name to the component's work directory, and compose mounts it into the backend. Even a deployment that changes only the config changes the startup environment variables, so the component restarts and reads the new config. `deploy.sh` resets these two and then merges every time, so no config from a previous deployment remains.

The Fast DDS profile XML (`greengrass/fastdds.xml`) is bundled as a component artifact like `compose.yml`, mounted at `/app/fastdds.xml` in the backend, and loaded via `FASTRTPS_DEFAULT_PROFILES_FILE`. It applies to both monitoring (rclpy) and recording (`ros2 bag record`). It currently disables Shared Memory and uses UDP only (with Isaac Sim and the like on the same PC, the container's `/dev/shm` is separate, so data does not arrive over Shared Memory; see [dds_gap.md](../../docs/domain/dds_gap.md#notes-on-shared-memory-transport)). It does not change often; to change it, release a new `COMPONENT_VERSION`. If the XML is broken, Fast DDS logs `XMLPARSER Error` and runs with the default settings.

The only recording config a device uses is the contents sent by the deployment. It is not bundled with the release, and there is no mechanism to override it with a file on the device (to prevent running with a config not visible in Fleet Console). If the deployment did not send the contents, the component fails instead of silently starting OpenLUTRA with defaults.

### Status

Created with the same `COMPONENT_VERSION` as OpenLutra and deployed together. Every 60 seconds it sends the following values to CloudWatch metrics (namespace `OpenLUTRA`, dimension `ThingName`).

| Metric | Contents |
|---|---|
| `Heartbeat` | Always 1. If it stops arriving, the device or the component has stopped |
| `DiskFreePercent` / `DiskFreeGB` | Free space at the recording data location (`OutputDir`). Recording data keeps accumulating, so this is the value to watch most |
| `OpenLutraUp` | Whether the OpenLUTRA API responded |
| `Recording` | Whether it is recording (`/api/recording/status`) |
| `MaxLossRate` | Maximum loss rate across subscribed topics (%, `/api/topics`) |
| `RecordedSeconds` / `PassedSeconds` | Length of recordings whose validation has finished, and the part of it whose result is `pass`. Sent once per recording, at the recording's start time (`/api/recordings`). Names of sent recordings are recorded in the component's work directory |

It calls `PutMetricData` directly with the Token Exchange Service's temporary credentials, without going through IoT Core MQTT and IoT rules. The IoT rule CloudWatch metric action cannot attach dimensions, so it cannot produce per-device metrics.

### LogManager

An AWS-provided component. Sends the nucleus logs and the OpenLutra and Status logs to CloudWatch Logs (`/aws/greengrass/...`) every 5 minutes. Logs can be investigated without visiting the site. `deploy.sh` includes its configuration in the deployment.

## Monitoring

| Aspect | Mechanism |
|---|---|
| Is it connected | "Status not arriving" if 10 minutes or more have passed since the last `Heartbeat` |
| Can it record | "Low disk space" if free space is below 5%. The loss rate and whether it is recording are also shown |
| Did the deployment succeed | Per-device deployment status in Fleet Console and `make status` |
| What happened | CloudWatch Logs sent by LogManager |
| Is the PC healthy | Nucleus telemetry (enabled by default). It is best-effort, so use `Heartbeat` for liveness |

The Dashboard's "Collection monitor" sums `RecordedSeconds` / `PassedSeconds` per hour and day to show recorded hours that passed validation and the pass rate, and estimates the days until the disk is full from how `DiskFreeGB` decreased over the last 3 days. Fleet Console (`console/`) makes the judgement by reading the metrics and Greengrass status, and sorts devices into the following 4 statuses (higher takes precedence).

| Status | Condition |
|---|---|
| Error | Status has not arrived for 10 minutes or more (disconnected), OpenLUTRA does not respond, the device is UNHEALTHY, or the OpenLUTRA component is not running |
| Warning | Free disk space below 5% or full within 3 days, loss rate above 2%, a deployment failed, or it stays on a version different from the deployment without updating (after a deployment is canceled or the device is moved between groups) |
| Updating | A deployment is being applied |
| OK | None of the above |

CloudWatch alarms and notifications are not included. When production needs notifications, decide how to create alarms (per device, or one for all with Metrics Insights) and add them.

## Devices

### Registration (`device/provision.sh`)

On the operator's PC, creates the Thing and certificate, attaches the IoT Policy, and adds the Thing to the Thing Group. Writes the certificate, private key, root CA, and endpoint into one directory, which is carried to the device. It contains the private key, so `provisioned/` is git-ignored. After handing it to the device, delete only the private key and keep the issue record (`metadata.json`: Thing, group, certificate, issue time).

To register many devices on site in production, use Fleet Provisioning (devices register themselves with a claim certificate).

### Setup (`device/setup.sh`)

On the edge PC (Ubuntu), installs Docker (including the compose plugin), Java, and `python3-venv` (a dependency of the Status component), installs the nucleus with `--provision false`, and registers it with systemd. `ggc_user` is created before the installer and added to the docker group, so docker is usable as soon as the first deployment arrives.

### Network

On a PC connected to both the robot's LAN and the internet, the default route must point to the internet side. If the robot LAN's DHCP hands out a gateway, traffic to AWS flows into the robot's LAN and the nucleus cannot connect. Communication with the robot stays within the same subnet, so make the robot-side NIC not accept a default route.

## State

The Terraform state lives locally (`infra/terraform.tfstate`, git-ignored). When several people run apply in production, use the S3 backend.
