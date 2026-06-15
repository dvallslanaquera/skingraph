resource "aws_efs_file_system" "data" {
  creation_token   = "${var.app_name}-data"
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"
  encrypted        = true

  tags = { Name = "${var.app_name}-efs" }
}

resource "aws_efs_mount_target" "data" {
  count           = 2
  file_system_id  = aws_efs_file_system.data.id
  subnet_id       = aws_subnet.public[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# Scoped access point for the Qdrant vector store.
# Mounting at /qdrant (EFS root) → /app/data/qdrant (container) means the
# static JSON files at /app/data/*.json (baked into the image) are NOT shadowed.
resource "aws_efs_access_point" "qdrant" {
  file_system_id = aws_efs_file_system.data.id

  root_directory {
    path = "/qdrant"
    creation_info {
      owner_uid   = 0
      owner_gid   = 0
      permissions = "755"
    }
  }

  tags = { Name = "${var.app_name}-qdrant-ap" }
}

# NOTE: users.db (SQLite) cannot be mounted via EFS — EFS mounts are directories,
# not files, and mounting a directory at /app/data/users.db would shadow the path.
# The DB is therefore ephemeral per task; user profiles are lost on task replacement.
# For persistence, migrate user_store.py to a managed DB (e.g. RDS Postgres).
