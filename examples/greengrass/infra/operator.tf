# What a person needs to release, deploy, register devices and run the console (the make targets
# other than provisioning this infrastructure). Add IAM users to the group; their access keys are
# created by hand so they never land in the Terraform state.
resource "aws_iam_group" "operator" {
  name = "open-lutra-operators"
}

resource "aws_iam_group_policy" "operator" {
  name  = "operate"
  group = aws_iam_group.operator.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "EcrPushAndCheck"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:DescribeImages",
        ]
        Resource = [for repo in aws_ecr_repository.image : repo.arn]
      },
      {
        Sid      = "Artifacts"
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:ListBucket"]
        Resource = aws_s3_bucket.artifacts.arn
      },
      {
        Sid      = "ArtifactObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.artifacts.arn}/*"
      },
      {
        # Components, deployments and core device status. Deployments run as IoT jobs on the
        # thing group, so these Greengrass actions also need the job, job execution and shadow
        # actions below (the "dependent actions" in the Greengrass V2 IAM reference).
        Sid    = "Greengrass"
        Effect = "Allow"
        Action = [
          "greengrass:CreateComponentVersion",
          "greengrass:DescribeComponent",
          "greengrass:GetComponent",
          "greengrass:ListComponents",
          "greengrass:ListComponentVersions",
          "greengrass:CreateDeployment",
          "greengrass:GetDeployment",
          "greengrass:ListDeployments",
          "greengrass:ListCoreDevices",
          "greengrass:GetCoreDevice",
          "greengrass:ListInstalledComponents",
          "greengrass:ListEffectiveDeployments",
        ]
        Resource = "*"
      },
      {
        Sid    = "IotForDeploymentsAndDevices"
        Effect = "Allow"
        Action = [
          "iot:CreateJob",
          "iot:UpdateJob",
          "iot:CancelJob",
          "iot:DescribeJob",
          "iot:DescribeJobExecution",
          "iot:GetThingShadow",
          "iot:UpdateThingShadow",
          "iot:DeleteThingShadow",
          "iot:DescribeThing",
          "iot:CreateThing",
          "iot:DescribeThingGroup",
          "iot:CreateThingGroup",
          "iot:ListThingGroups",
          "iot:AddThingToThingGroup",
          "iot:ListThingsInThingGroup",
          "iot:CreateKeysAndCertificate",
          "iot:AttachThingPrincipal",
          "iot:DescribeEndpoint",
        ]
        Resource = "*"
      },
      {
        Sid      = "AttachOnlyTheCoreDevicePolicy"
        Effect   = "Allow"
        Action   = "iot:AttachPolicy"
        Resource = aws_iot_policy.core_device.arn
      },
      {
        Sid      = "ConsoleMonitoring"
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricData", "sts:GetCallerIdentity"]
        Resource = "*"
      },
    ]
  })
}
