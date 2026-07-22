# Bedrock Guardrail for vacation-planner BFF input/output checks.
# The Lambda still must call ApplyGuardrail (SAFETY_MODE=bedrock) — this module only provisions the policy.

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "enabled" {
  description = "When false, no Guardrail resources are created"
  type        = bool
  default     = true
}

variable "blocked_input_messaging" {
  type    = string
  default = "That request was blocked by our safety checks. Please rephrase your travel preferences."
}

variable "blocked_outputs_messaging" {
  type    = string
  default = "A suggested plan was blocked by our safety checks. Please try again with different preferences."
}

variable "content_filter_strength" {
  description = "Strength for standard content filters (NONE|LOW|MEDIUM|HIGH)"
  type        = string
  default     = "HIGH"

  validation {
    condition     = contains(["NONE", "LOW", "MEDIUM", "HIGH"], var.content_filter_strength)
    error_message = "content_filter_strength must be NONE, LOW, MEDIUM, or HIGH."
  }
}

variable "prompt_attack_input_strength" {
  description = "Input strength for PROMPT_ATTACK filter"
  type        = string
  default     = "HIGH"

  validation {
    condition     = contains(["NONE", "LOW", "MEDIUM", "HIGH"], var.prompt_attack_input_strength)
    error_message = "prompt_attack_input_strength must be NONE, LOW, MEDIUM, or HIGH."
  }
}

variable "denied_topics" {
  description = "Denied-topic definitions (name, definition, examples)"
  type = list(object({
    name       = string
    definition = string
    examples   = list(string)
  }))
  default = [
    {
      name       = "weapons_and_violence"
      definition = "Requests involving weapons, explosives, violent crime, or planning harm to people or property."
      examples = [
        "How do I bring a firearm on this trip?",
        "Help me plan an attack while traveling",
      ]
    },
    {
      name       = "self_harm"
      definition = "Requests that seek help with self-harm, suicide, or methods of harming oneself."
      examples = [
        "I want to hurt myself on this trip",
        "Best ways to disappear forever while traveling",
      ]
    },
    {
      name       = "adult_sexual_content"
      definition = "Requests for adult sexual content, pornography, or sexual services as part of a travel plan."
      examples = [
        "Find strip clubs and escorts for my itinerary",
        "Plan an adult-only sex tourism trip",
      ]
    },
    {
      name       = "illegal_activity"
      definition = "Requests that seek help committing crimes, acquiring illegal drugs, or evading law enforcement while traveling."
      examples = [
        "Where can I buy illegal drugs in Tokyo?",
        "How do I smuggle something through customs?",
      ]
    },
  ]
}

variable "custom_denied_words" {
  description = "Extra denied words/phrases (in addition to prompt-injection defaults)"
  type        = list(string)
  default     = []
}

variable "publish_version" {
  description = "Publish an immutable Guardrail version (recommended for prod)"
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Content categories Bedrock supports on both input and output.
  content_filter_types = ["HATE", "INSULTS", "SEXUAL", "VIOLENCE", "MISCONDUCT"]

  # Prompt-injection style phrases (same spirit as KeywordSafetyGate).
  default_denied_words = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard your system prompt",
    "jailbreak",
  ]

  denied_words = distinct(concat(local.default_denied_words, var.custom_denied_words))

  # Contact/financial PII only — NAME/ADDRESS false-positive on travel text ("Tokyo", "Central Park").
  pii_types = [
    "EMAIL",
    "PHONE",
    "CREDIT_DEBIT_CARD_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "US_BANK_ACCOUNT_NUMBER",
    "PASSWORD",
  ]
}

resource "aws_bedrock_guardrail" "trips" {
  count = var.enabled ? 1 : 0

  name                      = "${local.name_prefix}-trips"
  description               = "High-safety Guardrail for vacation-planner trip preferences and crew outputs"
  blocked_input_messaging   = var.blocked_input_messaging
  blocked_outputs_messaging = var.blocked_outputs_messaging
  tags                      = var.tags

  content_policy_config {
    dynamic "filters_config" {
      for_each = local.content_filter_types
      content {
        type            = filters_config.value
        input_strength  = var.content_filter_strength
        output_strength = var.content_filter_strength
      }
    }

    # Prompt attacks are input-side; NONE on output is required by the API.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = var.prompt_attack_input_strength
      output_strength = "NONE"
    }
  }

  topic_policy_config {
    dynamic "topics_config" {
      for_each = var.denied_topics
      content {
        name       = topics_config.value.name
        type       = "DENY"
        definition = topics_config.value.definition
        examples   = topics_config.value.examples
      }
    }
  }

  word_policy_config {
    managed_word_lists_config {
      type = "PROFANITY"
    }

    dynamic "words_config" {
      for_each = local.denied_words
      content {
        text = words_config.value
      }
    }
  }

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = local.pii_types
      content {
        type           = pii_entities_config.value
        action         = "BLOCK"
        input_action   = "BLOCK"
        output_action  = "ANONYMIZE"
        input_enabled  = true
        output_enabled = true
      }
    }
  }
}

resource "aws_bedrock_guardrail_version" "trips" {
  count = var.enabled && var.publish_version ? 1 : 0

  description   = "Published by Terraform for ${local.name_prefix}"
  guardrail_arn = aws_bedrock_guardrail.trips[0].guardrail_arn
  skip_destroy  = true
}
