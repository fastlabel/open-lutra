#!/usr/bin/env bash
# Registers a core device in AWS IoT and writes a bundle (certificate, private
# key, endpoints) that setup.sh installs on the device. Run on an admin machine;
# the device itself never receives AWS credentials. The device joins THING_GROUP.
#
# metadata.json records which thing and group the certificate was issued for and
# when. It is kept after the private key is deleted, as the record of issued keys.
set -euo pipefail

: "${THING_NAME:?}" "${AWS_REGION:?}"
: "${THING_GROUP:?pass THING_GROUP=<thing group> for the device to join}"
cd "$(dirname "$0")/.."

bundle=${BUNDLE_DIR:-provisioned/$THING_NAME}
policy=$(scripts/infra-output.sh CORE_DEVICE_POLICY core_device_policy)
role_alias=$(scripts/infra-output.sh TES_ROLE_ALIAS token_exchange_role_alias)

if [ -e "$bundle" ]; then
  echo "$bundle already exists" >&2
  exit 1
fi
if aws iot describe-thing --thing-name "$THING_NAME" >/dev/null 2>&1; then
  echo "thing $THING_NAME already exists" >&2
  exit 1
fi

mkdir -p "$bundle"
chmod 700 "$bundle"

aws iot create-thing --thing-name "$THING_NAME" >/dev/null
cert_arn=$(aws iot create-keys-and-certificate --set-as-active \
  --certificate-pem-outfile "$bundle/device.pem.crt" \
  --private-key-outfile "$bundle/private.pem.key" \
  --query certificateArn --output text)
aws iot attach-policy --policy-name "$policy" --target "$cert_arn"
aws iot attach-thing-principal --thing-name "$THING_NAME" --principal "$cert_arn"
aws iot add-thing-to-thing-group --thing-name "$THING_NAME" --thing-group-name "$THING_GROUP"

curl -fsSL https://www.amazontrust.com/repository/AmazonRootCA1.pem -o "$bundle/AmazonRootCA1.pem"

cat >"$bundle/device.env" <<EOF
THING_NAME=$THING_NAME
AWS_REGION=$AWS_REGION
TES_ROLE_ALIAS=$role_alias
IOT_DATA_ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text)
IOT_CRED_ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:CredentialProvider --query endpointAddress --output text)
EOF

jq -n --arg thing "$THING_NAME" --arg group "$THING_GROUP" --arg cert "$cert_arn" \
  --arg created "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{thing: $thing, thing_group: $group, certificate_arn: $cert, created_at: $created}' >"$bundle/metadata.json"

echo "$THING_NAME registered in $THING_GROUP; bundle written to $bundle"
