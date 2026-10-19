#!/usr/bin/env bash
# Creates the OpenLUTRA and status component versions from images already
# pushed to ECR. Both components share COMPONENT_VERSION.
set -euo pipefail

: "${COMPONENT_NAME:?}" "${STATUS_COMPONENT_NAME:?}" "${COMPONENT_PUBLISHER:?}" "${COMPONENT_VERSION:?}" "${IMAGE_TAG:?}" "${PLATFORM:?}"
cd "$(dirname "$0")/.."

# The nucleus reads a hyphen in a version as an npm range, so pre-release versions never resolve.
if ! [[ "$COMPONENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "COMPONENT_VERSION must be MAJOR.MINOR.PATCH: $COMPONENT_VERSION" >&2
  exit 1
fi

case "$PLATFORM" in
  linux/amd64) ARCHITECTURE=amd64 ;;
  linux/arm64) ARCHITECTURE=aarch64 ;;
  *) echo "unsupported PLATFORM: $PLATFORM" >&2; exit 1 ;;
esac

REGISTRY=$(scripts/infra-output.sh ECR_REGISTRY registry)
bucket=$(scripts/infra-output.sh ARTIFACT_BUCKET artifact_bucket)
account=${REGISTRY%%.*}
region=$(cut -d. -f4 <<<"$REGISTRY")
export ARCHITECTURE REGISTRY

component_arn() {
  echo "arn:aws:greengrass:$region:$account:components:$1:versions:$COMPONENT_VERSION"
}

for name in "$COMPONENT_NAME" "$STATUS_COMPONENT_NAME"; do
  if out=$(aws greengrassv2 describe-component --arn "$(component_arn "$name")" 2>&1); then
    echo "$name $COMPONENT_VERSION already exists" >&2
    exit 1
  elif ! grep -q ResourceNotFoundException <<<"$out"; then
    echo "$out" >&2
    exit 1
  fi
done

for image in backend frontend; do
  aws ecr describe-images --repository-name "open-lutra-$image" \
    --image-ids imageTag="$IMAGE_TAG" --query 'imageDetails[0].imageTags' --output text >/dev/null
done

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# create <component name> <recipe template> <artifact>...
create() {
  local name=$1 template=$2 arn state
  shift 2
  arn=$(component_arn "$name")
  ARTIFACT_PREFIX="s3://$bucket/$name/$COMPONENT_VERSION"
  export ARTIFACT_PREFIX
  for artifact in "$@"; do
    aws s3 cp "$artifact" "$ARTIFACT_PREFIX/$(basename "$artifact")"
  done
  envsubst '$COMPONENT_NAME $STATUS_COMPONENT_NAME $COMPONENT_PUBLISHER $COMPONENT_VERSION $ARCHITECTURE $REGISTRY $IMAGE_TAG $ARTIFACT_PREFIX' \
    <"$template" >"$work/recipe.yaml"
  aws greengrassv2 create-component-version --inline-recipe "fileb://$work/recipe.yaml" --query arn --output text

  for _ in $(seq 30); do
    state=$(aws greengrassv2 describe-component --arn "$arn" --query status.componentState --output text)
    case "$state" in
      DEPLOYABLE) echo "$arn is deployable"; return ;;
      FAILED)
        aws greengrassv2 describe-component --arn "$arn" --query status.message --output text >&2
        exit 1 ;;
    esac
    sleep 2
  done
  echo "timed out waiting for $arn (state: $state)" >&2
  exit 1
}

create "$COMPONENT_NAME" greengrass/recipe.yaml \
  greengrass/compose.yml greengrass/fastdds.xml
create "$STATUS_COMPONENT_NAME" greengrass/status/recipe.yaml \
  greengrass/status/status.py greengrass/status/requirements.txt
