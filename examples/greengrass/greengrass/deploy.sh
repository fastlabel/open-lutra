#!/usr/bin/env bash
# Deploys a component version to THING_GROUP, together with the status
# component and LogManager (which uploads the nucleus and component logs to
# CloudWatch Logs). The deployment replaces the group's previous one.
#
# RECORDING_CONFIG (required) is the path of a recording config to send with the
# deployment; its content is written on the device, so a new config needs no new
# component version. CONFIGURATION, if set instead, is a JSON object merged into
# the OpenLUTRA component's default configuration. The recording config of the
# previous deployment is reset either way, so it never lingers.
set -euo pipefail

: "${COMPONENT_NAME:?}" "${STATUS_COMPONENT_NAME:?}" "${LOG_MANAGER_VERSION:?}" "${COMPONENT_VERSION:?}"
: "${THING_GROUP:?pass THING_GROUP=<thing group> to deploy to}"
cd "$(dirname "$0")/.."

if [ -n "${RECORDING_CONFIG:-}" ]; then
  CONFIGURATION=$(jq -n --arg name "$(basename "$RECORDING_CONFIG")" --rawfile content "$RECORDING_CONFIG" \
    '{RecordingConfigFile: $name, RecordingConfig: $content} | tojson' -r)
fi
: "${CONFIGURATION:?pass RECORDING_CONFIG=<recording config file> to deploy}"

target=$(aws iot describe-thing-group --thing-group-name "$THING_GROUP" --query thingGroupArn --output text)

components=$(jq -n --arg name "$COMPONENT_NAME" --arg status "$STATUS_COMPONENT_NAME" --arg version "$COMPONENT_VERSION" \
  --arg log_manager "$LOG_MANAGER_VERSION" --arg merge "$CONFIGURATION" '{
    ($name): {
      componentVersion: $version,
      configurationUpdate: {reset: ["/RecordingConfigFile", "/RecordingConfig"], merge: $merge}
    },
    ($status): {componentVersion: $version},
    "aws.greengrass.LogManager": {
      componentVersion: $log_manager,
      configurationUpdate: {merge: ({
        logsUploaderConfiguration: {
          systemLogsConfiguration: {uploadToCloudWatch: "true", minimumLogLevel: "INFO"},
          componentLogsConfigurationMap: {($name): {minimumLogLevel: "INFO"}, ($status): {minimumLogLevel: "INFO"}}
        },
        periodicUploadIntervalSec: "300"
      } | tojson)}
    }
  }')

aws greengrassv2 create-deployment \
  --target-arn "$target" \
  --deployment-name "$COMPONENT_NAME-$THING_GROUP" \
  --components "$components" \
  --query deploymentId --output text
