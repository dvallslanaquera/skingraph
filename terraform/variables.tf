variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Name prefix for all AWS resources"
  type        = string
  default     = "skincare-coach"
}

variable "google_api_key" {
  description = "Google Gemini API key — stored in Secrets Manager, injected at task start"
  type        = string
  sensitive   = true
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. 'latest', 'v1.2.0')"
  type        = string
  default     = "latest"
}

variable "task_cpu" {
  description = "Fargate CPU units (1024 = 1 vCPU). Sized for the ONNX embedding model + API."
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = "Fargate memory in MiB. 2048 covers the embedding model + LangGraph state."
  type        = number
  default     = 2048
}

variable "desired_count" {
  description = "Number of API tasks to run concurrently. Keep at 1: Qdrant on-disk is single-writer."
  type        = number
  default     = 1
}
