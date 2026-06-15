output "ecr_repository_url" {
  value       = aws_ecr_repository.api.repository_url
  description = "Push your api image here before starting the service"
}

output "api_endpoint" {
  value       = "http://${aws_lb.api.dns_name}"
  description = "Public HTTP endpoint for the SkinGraph API (add HTTPS via ACM + listener rule)"
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "build_index_command" {
  description = "Run once after first image push to seed the Qdrant vector store on EFS"
  value       = <<-EOT
    aws ecs run-task \
      --region ${var.aws_region} \
      --cluster ${aws_ecs_cluster.main.name} \
      --task-definition ${aws_ecs_task_definition.api.family} \
      --launch-type FARGATE \
      --network-configuration 'awsvpcConfiguration={subnets=["${aws_subnet.public[0].id}"],securityGroups=["${aws_security_group.ecs_tasks.id}"],assignPublicIp=ENABLED}' \
      --overrides '{"containerOverrides":[{"name":"api","command":["python","scripts/build_index.py"]}]}'
  EOT
}
