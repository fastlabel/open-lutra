resource "aws_iot_role_alias" "token_exchange" {
  alias    = "open-lutra-gg-token-exchange"
  role_arn = aws_iam_role.token_exchange.arn
}

# Attached to each core device certificate. Scoped to the device's own thing
# name; the trailing * covers the extra MQTT connections the nucleus opens.
resource "aws_iot_policy" "core_device" {
  name = "open-lutra-gg-core-device"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "iot:Connect"
        Resource = "arn:aws:iot:${var.region}:${local.account_id}:client/$${iot:Connection.Thing.ThingName}*"
      },
      {
        Effect   = "Allow"
        Action   = ["iot:Publish", "iot:Receive"]
        Resource = "arn:aws:iot:${var.region}:${local.account_id}:topic/$aws/things/$${iot:Connection.Thing.ThingName}*/*"
      },
      {
        Effect   = "Allow"
        Action   = "iot:Subscribe"
        Resource = "arn:aws:iot:${var.region}:${local.account_id}:topicfilter/$aws/things/$${iot:Connection.Thing.ThingName}*/*"
      },
      {
        Effect   = "Allow"
        Action   = "iot:AssumeRoleWithCertificate"
        Resource = aws_iot_role_alias.token_exchange.arn
      },
      {
        Effect = "Allow"
        Action = [
          "greengrass:GetComponentVersionArtifact",
          "greengrass:ResolveComponentCandidates",
          "greengrass:GetDeploymentConfiguration",
          "greengrass:ListThingGroupsForCoreDevice",
        ]
        Resource = "*"
      },
    ]
  })
}
