data "aws_caller_identity" "current" {}

# The account's one GitHub OIDC provider belongs to CloudOps. Read it, never create a second.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  account      = data.aws_caller_identity.current.account_id
  state_bucket = "deskville-tfstate-${local.account}"
  sub_by_name  = "repo:${var.owner}/${var.repo}"
  sub_by_id    = "repo:${var.owner}@${var.owner_id}/${var.repo}@${var.repo_id}"
  boundary_arn = "arn:aws:iam::${local.account}:policy/deskville-boundary"
}

# ---------------------------------------------------------------------------
# Permissions boundary: every role CI creates must carry it.
# Whatever policy a role gets, it can never exceed this.
# ---------------------------------------------------------------------------
resource "aws_iam_policy" "boundary" {
  name        = "deskville-boundary"
  description = "Ceiling for every role created by Deskville CI"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowWorkloadServices"
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      },
      {
        Sid      = "NoIdentityOrAccountChanges"
        Effect   = "Deny"
        Action   = ["iam:*", "organizations:*", "account:*", "sso:*", "identitystore:*"]
        Resource = "*"
      },
      {
        Sid      = "NoTouchingTerraformState"
        Effect   = "Deny"
        Action   = "s3:*"
        Resource = ["arn:aws:s3:::${local.state_bucket}", "arn:aws:s3:::${local.state_bucket}/*"]
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Plan role: pull requests only. Read-only, plus the state lock file.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "plan" {
  name                 = "deskville-github-plan"
  description          = "terraform plan on pull requests of ${var.owner}/${var.repo}"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "${local.sub_by_name}:pull_request",
            "${local.sub_by_id}:pull_request",
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "plan_state" {
  name = "state-and-limits"
  role = aws_iam_role.plan.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "StateLockFile"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::${local.state_bucket}/*.tflock"
      },
      {
        # ReadOnlyAccess can read every object in the account, including other
        # projects' data. The plan role only needs the state bucket.
        Sid         = "DenyReadingOtherObjects"
        Effect      = "Deny"
        Action      = "s3:GetObject"
        NotResource = "arn:aws:s3:::${local.state_bucket}/*"
      },
      {
        Sid      = "DenySecretValues"
        Effect   = "Deny"
        Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = "*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Apply role: only from the 'production' environment (manual approval).
# Builds infrastructure; in IAM it only touches deskville-* roles, and only
# with the boundary attached. It can never modify the CI roles or the boundary.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "apply" {
  name                 = "deskville-github-apply"
  description          = "terraform apply from the production environment of ${var.owner}/${var.repo}"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "${local.sub_by_name}:environment:production",
            "${local.sub_by_id}:environment:production",
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "apply_poweruser" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy" "apply_iam" {
  name = "scoped-iam"
  role = aws_iam_role.apply.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadIam"
        Effect   = "Allow"
        Action   = ["iam:Get*", "iam:List*"]
        Resource = "*"
      },
      {
        Sid      = "CreateRolesOnlyWithBoundary"
        Effect   = "Allow"
        Action   = ["iam:CreateRole", "iam:PutRolePermissionsBoundary"]
        Resource = "arn:aws:iam::${local.account}:role/deskville-*"
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = local.boundary_arn }
        }
      },
      {
        Sid    = "ManageOwnRoles"
        Effect = "Allow"
        Action = [
          "iam:DeleteRole", "iam:UpdateRole", "iam:UpdateRoleDescription", "iam:UpdateAssumeRolePolicy",
          "iam:TagRole", "iam:UntagRole", "iam:PassRole",
          "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
        ]
        Resource = "arn:aws:iam::${local.account}:role/deskville-*"
      },
      {
        Sid    = "ManageOwnPolicies"
        Effect = "Allow"
        Action = [
          "iam:CreatePolicy", "iam:DeletePolicy", "iam:CreatePolicyVersion", "iam:DeletePolicyVersion",
          "iam:SetDefaultPolicyVersion", "iam:TagPolicy", "iam:UntagPolicy",
        ]
        Resource = "arn:aws:iam::${local.account}:policy/deskville-*"
      },
      {
        Sid      = "ServiceLinkedRoles"
        Effect   = "Allow"
        Action   = "iam:CreateServiceLinkedRole"
        Resource = "*"
      },
      {
        Sid      = "NeverRemoveABoundary"
        Effect   = "Deny"
        Action   = "iam:DeleteRolePermissionsBoundary"
        Resource = "*"
      },
      {
        Sid    = "DenySelfModification"
        Effect = "Deny"
        Action = [
          "iam:Create*", "iam:Delete*", "iam:Update*", "iam:Put*", "iam:Attach*", "iam:Detach*",
          "iam:Tag*", "iam:Untag*", "iam:SetDefaultPolicyVersion",
        ]
        Resource = [
          "arn:aws:iam::${local.account}:role/deskville-github-*",
          local.boundary_arn,
        ]
      }
    ]
  })
}

output "plan_role_arn" {
  value = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  value = aws_iam_role.apply.arn
}
