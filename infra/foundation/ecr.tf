# ---------------------------------------------------------------------------
# Container registry for the API (layer 5.2, D36). Always on and cheap (a few
# hundred MB of images), so it lives in foundation; the containers that run
# the images are switched on and off with the lab (5.4).
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "api" {
  name                 = "${var.name}-api"
  image_tag_mutability = "IMMUTABLE" # a published tag always means the same image
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true # basic scanning: free, findings visible in CI
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Untagged images go after a day"
        selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 1 }
        action       = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the 10 most recent images"
        selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
        action       = { type = "expire" }
      }
    ]
  })
}
