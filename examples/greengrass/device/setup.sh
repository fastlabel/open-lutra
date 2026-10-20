#!/usr/bin/env bash
# Sets up an Ubuntu machine as a Greengrass core device for OpenLUTRA, using a
# bundle written by provision.sh. Run as root: setup.sh <bundle-dir>
set -euo pipefail

bundle=${1:?usage: setup.sh <bundle-dir>}
GREENGRASS_ROOT=/greengrass/v2

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi
if [ -d "$GREENGRASS_ROOT" ]; then
  echo "$GREENGRASS_ROOT already exists; this device is already set up" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$bundle/device.env"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl unzip python3-venv

command -v java >/dev/null || apt-get install -y openjdk-17-jre-headless

if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
docker compose version >/dev/null

# Created before the installer so that ggc_user can reach Docker as soon as the
# first deployment arrives.
getent group ggc_group >/dev/null || groupadd --system ggc_group
id ggc_user >/dev/null 2>&1 || useradd --system --gid ggc_group --create-home ggc_user
usermod -aG docker ggc_user

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsSL https://d2s8p88vqu9w66.cloudfront.net/releases/greengrass-nucleus-latest.zip -o "$work/nucleus.zip"
unzip -q "$work/nucleus.zip" -d "$work/installer"
nucleus_version=$(java -jar "$work/installer/lib/Greengrass.jar" --version | sed 's/.*v//')

install -d -m 0755 /greengrass "$GREENGRASS_ROOT"
install -m 0644 "$bundle/device.pem.crt" "$bundle/AmazonRootCA1.pem" "$GREENGRASS_ROOT/"
install -m 0600 "$bundle/private.pem.key" "$GREENGRASS_ROOT/"

cat >"$work/config.yaml" <<EOF
system:
  certificateFilePath: $GREENGRASS_ROOT/device.pem.crt
  privateKeyPath: $GREENGRASS_ROOT/private.pem.key
  rootCaPath: $GREENGRASS_ROOT/AmazonRootCA1.pem
  rootpath: $GREENGRASS_ROOT
  thingName: $THING_NAME
services:
  aws.greengrass.Nucleus:
    componentType: NUCLEUS
    version: $nucleus_version
    configuration:
      awsRegion: $AWS_REGION
      iotRoleAlias: $TES_ROLE_ALIAS
      iotDataEndpoint: $IOT_DATA_ENDPOINT
      iotCredEndpoint: $IOT_CRED_ENDPOINT
EOF

java -Droot="$GREENGRASS_ROOT" -Dlog.store=FILE \
  -jar "$work/installer/lib/Greengrass.jar" \
  --init-config "$work/config.yaml" \
  --component-default-user ggc_user:ggc_group \
  --setup-system-service true
