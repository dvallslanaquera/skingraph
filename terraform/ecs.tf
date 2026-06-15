resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = 7
}

resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # enable for production; incurs CloudWatch Metrics cost
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.app_name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  # Mount the Qdrant EFS access point at /app/data/qdrant.
  # Only that subdirectory is shadowed; /app/data/*.json (baked in) remain accessible.
  volume {
    name = "qdrant-efs"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.data.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.qdrant.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [{ containerPort = 8000, protocol = "tcp" }]

      mountPoints = [{
        sourceVolume  = "qdrant-efs"
        containerPath = "/app/data/qdrant"
        readOnly      = false
      }]

      # ECS agent fetches this from Secrets Manager before the container starts.
      # load_dotenv() in main.py is a no-op when GOOGLE_API_KEY is already in env.
      secrets = [{
        name      = "GOOGLE_API_KEY"
        valueFrom = aws_secretsmanager_secret.google_api_key.arn
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      # The embedding model is pre-baked into the image (see Dockerfile); allow
      # extra time on cold start for Qdrant to open the EFS-backed store.
      startTimeout = 120
      stopTimeout  = 30
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${var.app_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true # tasks reach ECR, Gemini, and HuggingFace without a NAT gateway
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.execution_managed,
  ]
}
