resource "aws_ecr_repository" "image" {
  for_each = local.images

  name = "open-lutra-${each.key}"
  # A tag always points at the same image, so a component version keeps
  # resolving to the backend/frontend pair it was released with.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
