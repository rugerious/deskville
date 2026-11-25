# ---------------------------------------------------------------------------
# Residents' sign-in (layer 5.3, D35, D37). One user pool for every council;
# each user carries custom:tenant, which the app client can READ but never
# WRITE: only an administrator sets a user's council. Always on: Cognito costs
# nothing at this scale and holds no hourly resource.
# ---------------------------------------------------------------------------
resource "aws_cognito_user_pool" "residents" {
  name                = "${var.name}-residents"
  user_pool_tier      = "LITE"
  deletion_protection = "ACTIVE"
  mfa_configuration   = "OFF" # demo users only; a real service would require it

  # Nobody signs themselves up: accounts are created by an administrator,
  # which is where a user's council is decided.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 1
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }

  schema {
    name                     = "tenant"
    attribute_data_type      = "String"
    mutable                  = true # by an administrator; the app client below can't write it
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 1
      max_length = 32
    }
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name            = "${var.name}-web"
  user_pool_id    = aws_cognito_user_pool.residents.id
  generate_secret = false # a browser can't keep a secret

  # SRP for the sites (layer 7); USER_PASSWORD_AUTH for the tests from the laptop.
  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH", "ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  read_attributes  = ["custom:tenant", "name"]
  write_attributes = ["name"] # NOT custom:tenant: a user can never move themselves to another council

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 1
  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }
}
