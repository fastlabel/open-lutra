output "registry" {
  value = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

output "artifact_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "token_exchange_role_alias" {
  value = aws_iot_role_alias.token_exchange.alias
}

output "core_device_policy" {
  value = aws_iot_policy.core_device.name
}

output "operator_group" {
  value = aws_iam_group.operator.name
}
