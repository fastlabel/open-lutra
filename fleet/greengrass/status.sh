#!/usr/bin/env bash
# Lists the devices in THING_GROUP, or in every thing group when it is not set, with
# the OpenLUTRA version each one runs and the status of its latest deployment.
set -euo pipefail

: "${COMPONENT_NAME:?}"
cd "$(dirname "$0")/.."

groups=${THING_GROUP:-$(aws iot list-thing-groups --query 'thingGroups[].groupName' --output text)}

{
  printf 'GROUP\tDEVICE\tHEALTH\tVERSION\tSTATE\tDEPLOYMENT\n'
  for group in $groups; do
    target=$(aws iot describe-thing-group --thing-group-name "$group" --query thingGroupArn --output text)
    aws greengrassv2 list-core-devices --thing-group-arn "$target" \
      --query 'coreDevices[].[coreDeviceThingName,status]' --output text |
      while read -r thing health; do
        read -r version state < <(aws greengrassv2 list-installed-components --core-device-thing-name "$thing" --output json |
          jq -r --arg name "$COMPONENT_NAME" \
            '.installedComponents | map(select(.componentName == $name)) | first // {} | "\(.componentVersion // "-") \(.lifecycleState // "-")"')
        deployment=$(aws greengrassv2 list-effective-deployments --core-device-thing-name "$thing" --output json |
          jq -r '.effectiveDeployments | max_by(.modifiedTimestamp) | .coreDeviceExecutionStatus // "-"')
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$group" "$thing" "$health" "$version" "$state" "$deployment"
      done
  done
} | column -t -s $'\t'
