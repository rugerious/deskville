# ---------------------------------------------------------------------------
# The API on the internet (layer 5.4, D39). Part of the lab stack: the load
# balancer and the containers are billed by the hour, so they come up and go
# down with the database. Everything always-on (certificate, registry, Cognito)
# lives in foundation and is only read here.
#
#   resident ──HTTPS──▶ ALB (public subnets) ──8080──▶ 2 API tasks (ARM, 2 AZs)
#                                                          ├─5432─▶ RDS (as deskville_app, IAM token)
#                                                          └─443──▶ Bedrock Titan, Cognito keys, ECR, logs
# ---------------------------------------------------------------------------
# aws_caller_identity.current and local.boundary_arn are declared in bastion.tf.
data "aws_region" "current" {}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  tags = { Tier = "public" }
}

data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

data "aws_acm_certificate" "main" {
  domain      = var.domain_name
  statuses    = ["ISSUED"]
  most_recent = true
}

data "aws_ecr_repository" "api" {
  name = "${var.name}-api"
}

# The newest image CI pushed (after tests, approval and a scan with no CRITICAL),
# pinned by digest: the task runs exactly that image.
data "aws_ecr_image" "api" {
  repository_name = data.aws_ecr_repository.api.name
  most_recent     = true
}

data "aws_cognito_user_pools" "residents" {
  name = "${var.name}-residents"
}

data "aws_ssm_parameter" "guardrail_id" {
  name = "/${var.name}/guardrail/id"
}

data "aws_ssm_parameter" "guardrail_version" {
  name = "/${var.name}/guardrail/version"
}

data "aws_cognito_user_pool_clients" "web" {
  user_pool_id = data.aws_cognito_user_pools.residents.ids[0]
}

locals {
  api_host      = "api.${var.domain_name}"
  api_image     = "${data.aws_ecr_repository.api.repository_url}@${data.aws_ecr_image.api.image_digest}"
  pool_id       = data.aws_cognito_user_pools.residents.ids[0]
  web_client_id = data.aws_cognito_user_pool_clients.web.client_ids[index(data.aws_cognito_user_pool_clients.web.client_names, "${var.name}-web")]
  titan_arn     = "arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/amazon.titan-embed-text-v2:0"
  nova_lite_arn = "arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/amazon.nova-lite-v1:0"
  guardrail_arn = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:guardrail/${data.aws_ssm_parameter.guardrail_id.insecure_value}"
}

# --- network: who may talk to whom ------------------------------------------
resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "Public HTTPS (and HTTP, only to redirect)"
  vpc_id      = data.aws_vpc.main.id
  tags        = { Name = "${var.name}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS from the internet"
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "HTTP, answered only with a redirect to HTTPS"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  description                  = "To the API tasks only"
}

resource "aws_security_group" "tasks" {
  name        = "${var.name}-api-tasks"
  description = "API tasks: inbound only from the load balancer"
  vpc_id      = data.aws_vpc.main.id
  tags        = { Name = "${var.name}-api-tasks" }
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  description                  = "From the load balancer only"
}

resource "aws_vpc_security_group_egress_rule" "tasks_https" {
  security_group_id = aws_security_group.tasks.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Bedrock, Cognito keys, ECR, CloudWatch Logs (no NAT: public IP)"
}

resource "aws_vpc_security_group_egress_rule" "tasks_to_db" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL"
}

resource "aws_vpc_security_group_ingress_rule" "db_from_tasks" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from the API tasks"
}

# --- load balancer -----------------------------------------------------------
resource "aws_lb" "api" {
  name                       = "${var.name}-api"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = data.aws_subnets.public.ids
  drop_invalid_header_fields = true
  enable_deletion_protection = false # lab: destroyed after every session
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.name}-api"
  port                 = 8080
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = data.aws_vpc.main.id
  deregistration_delay = 15

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = data.aws_acm_certificate.main.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = local.api_host
  type    = "A"

  alias {
    name                   = aws_lb.api.dns_name
    zone_id                = aws_lb.api.zone_id
    evaluate_target_health = true
  }
}

# --- who the containers are ------------------------------------------------------
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}-api"
  retention_in_days = 7
}

resource "aws_iam_role" "api_execution" {
  name                 = "${var.name}-api-execution"
  description          = "ECS agent: pull the API image, write its logs"
  permissions_boundary = local.boundary_arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "api_execution" {
  role       = aws_iam_role.api_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "api_task" {
  name                 = "${var.name}-api-task"
  description          = "The API itself: connect to the database as deskville_app, embed with Titan, answer with Nova Lite, check with the guardrail"
  permissions_boundary = local.boundary_arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "api_task" {
  name = "least-privilege"
  role = aws_iam_role.api_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DatabaseAsTheAppRoleOnly"
        Effect   = "Allow"
        Action   = "rds-db:connect"
        Resource = "arn:aws:rds-db:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_db_instance.main.resource_id}/deskville_app"
      },
      {
        Sid      = "EmbedQueriesWithTitan"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = local.titan_arn
      },
      {
        Sid      = "AnswerWithNovaLiteInLondonOnly"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = local.nova_lite_arn
      },
      {
        Sid      = "CheckQuestionsAndAnswersWithTheResidentsGuardrail"
        Effect   = "Allow"
        Action   = "bedrock:ApplyGuardrail"
        Resource = local.guardrail_arn
      }
    ]
  })
}

# --- the containers ----------------------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.api_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name         = "api"
    image        = local.api_image
    essential    = true
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "AWS_REGION", value = data.aws_region.current.region },
      { name = "COGNITO_USER_POOL_ID", value = local.pool_id },
      { name = "COGNITO_APP_CLIENT_ID", value = local.web_client_id },
      { name = "SITE_DOMAIN", value = var.domain_name },
      { name = "GUARDRAIL_ID", value = data.aws_ssm_parameter.guardrail_id.insecure_value },
      { name = "GUARDRAIL_VERSION", value = data.aws_ssm_parameter.guardrail_version.insecure_value },
      { name = "DB_HOST", value = aws_db_instance.main.address },
      { name = "DB_PORT", value = tostring(aws_db_instance.main.port) },
      { name = "DB_NAME", value = aws_db_instance.main.db_name },
      { name = "DB_USER", value = "deskville_app" },
      { name = "DB_IAM_AUTH", value = "true" },
      { name = "DB_SSLMODE", value = "verify-full" },
      { name = "DB_SSLROOTCERT", value = "/app/rds-global-bundle.pem" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = data.aws_region.current.region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name                              = "${var.name}-api"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.api.arn
  desired_count                     = var.api_desired_count
  health_check_grace_period_seconds = 30
  wait_for_steady_state             = true # the apply only succeeds once the tasks are healthy

  # One task always on regular Fargate; the rest on Spot (cheaper, can be reclaimed).
  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    base              = 1
    weight            = 1
  }
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }

  network_configuration {
    subnets          = data.aws_subnets.public.ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true # no NAT gateway (D5); inbound is still only from the ALB
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8080
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https, aws_ecs_cluster_capacity_providers.main]
}
