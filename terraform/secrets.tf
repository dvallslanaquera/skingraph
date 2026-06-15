resource "aws_secretsmanager_secret" "google_api_key" {
  name                    = "${var.app_name}/google-api-key"
  description             = "Google Gemini API key injected into the ECS task at runtime"
  recovery_window_in_days = 0 # allow immediate deletion on terraform destroy
}

resource "aws_secretsmanager_secret_version" "google_api_key" {
  secret_id     = aws_secretsmanager_secret.google_api_key.id
  secret_string = var.google_api_key
}
