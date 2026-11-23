variable "owner" {
  type    = string
  default = "rugerious"
}

variable "repo" {
  type    = string
  default = "deskville"
}

# Immutable IDs: GitHub OIDC tokens may carry repo:owner@id/name@id:...
# (CloudOps bug 28). Not secrets: anyone can read them from the GitHub API.
variable "owner_id" {
  type    = string
  default = "280082370"
}

variable "repo_id" {
  type    = string
  default = "1469031807"
}
