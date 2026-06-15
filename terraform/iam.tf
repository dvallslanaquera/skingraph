data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ── Execution role ──────────────────────────────────────────────────────────
# Used by the ECS agent (not the container process) to:
#   - Pull the image from ECR
#   - Write logs to CloudWatch
#   - Fetch the GOOGLE_API_KEY secret from Secrets Manager at task start

resource "aws_iam_role" "execution" {
  name               = "${var.app_name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_api_key" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.google_api_key.arn]
  }
}

resource "aws_iam_role_policy" "execution_read_secret" {
  name   = "read-google-api-key"
  role   = aws_iam_role.execution.name
  policy = data.aws_iam_policy_document.read_api_key.json
}

# ── Task role ───────────────────────────────────────────────────────────────
# The identity of the running container process.
# Needs EFS access for the Qdrant vector store mount.

resource "aws_iam_role" "task" {
  name               = "${var.app_name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "task_efs" {
  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite",
      "elasticfilesystem:ClientRootAccess",
    ]
    resources = [aws_efs_file_system.data.arn]
  }
}

resource "aws_iam_role_policy" "task_efs" {
  name   = "efs-qdrant-access"
  role   = aws_iam_role.task.name
  policy = data.aws_iam_policy_document.task_efs.json
}
