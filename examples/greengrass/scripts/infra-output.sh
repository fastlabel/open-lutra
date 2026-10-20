#!/usr/bin/env bash
# Prints one infrastructure value: the environment variable if set, else the same key in
# .env, else the Terraform output. The Terraform state lives only where `terraform apply`
# ran, so other machines release and deploy with the values written in .env.
# Usage: scripts/infra-output.sh <ENV_VAR> <terraform output name>
set -euo pipefail

var=$1 output=$2
cd "$(dirname "$0")/.."

value=${!var:-}
if [ -z "$value" ] && [ -f .env ]; then
  value=$(sed -n "s/^${var}=//p" .env | tail -n 1)
  value=${value%\"} value=${value#\"}
fi
if [ -z "$value" ]; then
  value=$(terraform -chdir=infra output -raw "$output")
fi
printf '%s\n' "$value"
