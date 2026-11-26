# ---------------------------------------------------------------------------
# Residents' guardrail (layer 6.4, D43). Bedrock checks the question on the way
# in and the answer on the way out. Always on: it costs nothing until it is
# used (charged per text unit checked), like the certificate and Cognito.
# Classic tier only: Standard needs cross-region routing, and Deskville's data
# stays in London (D3).
# ---------------------------------------------------------------------------
resource "aws_bedrock_guardrail" "residents" {
  name        = "${var.name}-residents"
  description = "Council assistant: prompt attacks, harmful content, off-limits advice, personal identifiers, grounding"

  blocked_input_messaging   = "Sorry, I can only help with everyday council services, and please don't share bank, card or National Insurance numbers here. Try asking about bins, council tax, parking or licences."
  blocked_outputs_messaging = "Sorry, I couldn't give a reliable answer from the council's information. Please check the council's website or contact the council."

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE" # prompt attacks are only checked on input
    }
    filters_config {
      type            = "HATE"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    tier_config {
      tier_name = "CLASSIC"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "personal_legal_advice"
      type       = "DENY"
      definition = "Advice on whether a person should take legal action, how likely they are to win a legal case, or what their legal rights are in a personal dispute."
      examples   = ["Should I take my neighbour to court?", "Will I win if I sue the council?"]
    }
    topics_config {
      name       = "medical_advice"
      type       = "DENY"
      definition = "Diagnosis of symptoms, or recommendations about medicines, treatments or doses."
      examples   = ["What medicine should I take for my headache?", "Is this rash serious?"]
    }
    topics_config {
      name       = "investment_advice"
      type       = "DENY"
      definition = "Recommendations about personal investments, savings products, pensions, loans or cryptocurrency."
      examples   = ["Should I invest my savings in crypto?", "Which pension should I choose?"]
    }
    topics_config {
      name       = "political_opinion"
      type       = "DENY"
      definition = "Opinions or recommendations about political parties, politicians, candidates or how to vote."
      examples   = ["Which party should I vote for in the local elections?", "Is the council leader doing a good job?"]
    }
    tier_config {
      tier_name = "CLASSIC"
    }
  }

  # Personal identifiers a council assistant must never receive or repeat.
  # Phone numbers and email addresses are NOT here: the councils' own are public
  # and are part of good answers.
  sensitive_information_policy_config {
    pii_entities_config {
      type   = "UK_NATIONAL_INSURANCE_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "UK_NATIONAL_HEALTH_SERVICE_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_CVV"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "INTERNATIONAL_BANK_ACCOUNT_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "PASSWORD"
      action = "BLOCK"
    }
  }

  # The answer must be supported by the sources (and tool results) it was given,
  # and must answer the question. Thresholds fixed BEFORE the accuracy run.
  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = 0.7
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = 0.5
    }
  }
}

# A numbered, immutable version for the API to pin; a new one is cut whenever the
# guardrail changes. Old versions are kept so a running API never loses its own.
resource "aws_bedrock_guardrail_version" "residents" {
  guardrail_arn = aws_bedrock_guardrail.residents.guardrail_arn
  description   = "Cut by Terraform when the guardrail changes"
  skip_destroy  = true

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.residents]
  }
}

# Published for the lab stack, which reads them when it starts the API (the provider
# has no guardrail data source). Plain strings, nothing secret; SSM standard tier is free.
resource "aws_ssm_parameter" "guardrail_id" {
  name  = "/${var.name}/guardrail/id"
  type  = "String"
  value = aws_bedrock_guardrail.residents.guardrail_id
}

resource "aws_ssm_parameter" "guardrail_version" {
  name  = "/${var.name}/guardrail/version"
  type  = "String"
  value = aws_bedrock_guardrail_version.residents.version
}
