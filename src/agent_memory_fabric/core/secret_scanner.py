"""Secret scanner: detect API keys, tokens, and credentials before persisting to memory."""

from __future__ import annotations

import re
from dataclasses import dataclass


class SecretDetectedError(Exception):
    """Raised when content contains detected secrets and write is rejected."""

    def __init__(self, matches: list[SecretMatch]):
        self.matches = matches
        descriptions = ", ".join(m.description for m in matches[:3])
        super().__init__(f"Content contains potential secrets: {descriptions}. Write rejected.")


@dataclass
class SecretMatch:
    rule_id: str
    description: str


@dataclass
class _SecretRule:
    rule_id: str
    description: str
    pattern: re.Pattern


_RULES: list[_SecretRule] = []


def _add(rule_id: str, description: str, pattern: str, flags: int = 0) -> None:
    _RULES.append(_SecretRule(rule_id=rule_id, description=description, pattern=re.compile(pattern, flags)))


# AWS
_add("aws-access-key-id", "AWS Access Key ID", r"\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b")
_add("aws-secret-access-key", "AWS Secret Access Key", r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key[\s=:]+['\"]?([A-Za-z0-9/+=]{40})['\"]?")

# GitHub
_add("github-pat", "GitHub Personal Access Token", r"\b(ghp_[0-9a-zA-Z]{36})\b")
_add("github-fine-grained-pat", "GitHub Fine-Grained PAT", r"\b(github_pat_[0-9a-zA-Z_]{82})\b")
_add("github-oauth", "GitHub OAuth Token", r"\b(gho_[0-9a-zA-Z]{36})\b")
_add("github-app-token", "GitHub App Token", r"\b(ghu_[0-9a-zA-Z]{36})\b")
_add("github-refresh-token", "GitHub Refresh Token", r"\b(ghr_[0-9a-zA-Z]{36})\b")

# GitLab
_add("gitlab-pat", "GitLab Personal Access Token", r"\b(glpat-[0-9a-zA-Z\-_]{20,})\b")

# Slack
_add("slack-bot-token", "Slack Bot Token", r"\b(xoxb-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,})\b")
_add("slack-user-token", "Slack User Token", r"\b(xoxp-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,})\b")
_add("slack-app-token", "Slack App Token", r"\b(xapp-[0-9]-[A-Z0-9]{10,}-[0-9]{10,}-[a-z0-9]{64})\b")
_add("slack-webhook", "Slack Webhook URL", r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[a-zA-Z0-9]{24,}")

# AI APIs
_add("openai-api-key", "OpenAI API Key", r"\b(sk-[a-zA-Z0-9]{20,}T3BlbkFJ[a-zA-Z0-9]{20,})\b")
_add("anthropic-api-key", "Anthropic API Key", r"\b(sk-ant-[a-zA-Z0-9\-_]{80,})\b")
_add("huggingface-token", "HuggingFace Access Token", r"\b(hf_[a-zA-Z0-9]{34,})\b")

# Payment
_add("stripe-secret-key", "Stripe Secret Key", r"\b(sk_live_[0-9a-zA-Z]{24,})\b")
_add("stripe-restricted-key", "Stripe Restricted Key", r"\b(rk_live_[0-9a-zA-Z]{24,})\b")

# Infrastructure
_add("npm-access-token", "NPM Access Token", r"\b(npm_[0-9a-zA-Z]{36})\b")
_add("pypi-upload-token", "PyPI Upload Token", r"\b(pypi-[a-zA-Z0-9\-_]{100,})\b")
_add("sendgrid-api-key", "SendGrid API Key", r"\b(SG\.[a-zA-Z0-9\-_]{22,}\.[a-zA-Z0-9\-_]{43,})\b")
_add("twilio-api-key", "Twilio API Key", r"\b(SK[0-9a-fA-F]{32})\b")
_add("mailgun-api-key", "Mailgun API Key", r"\b(key-[0-9a-zA-Z]{32})\b")

# Cloud
_add("gcp-api-key", "Google Cloud API Key", r"\b(AIza[0-9A-Za-z\-_]{35})\b")
_add("digitalocean-pat", "DigitalOcean PAT", r"\b(dop_v1_[a-f0-9]{64})\b")
_add("digitalocean-access-token", "DigitalOcean Access Token", r"\b(doo_v1_[a-f0-9]{64})\b")

# Observability
_add("grafana-api-key", "Grafana API Key", r"\b(eyJrIjoi[A-Za-z0-9+/=]{40,})\b")
_add("sentry-auth-token", "Sentry Auth Token", r"\b(sntrys_[a-zA-Z0-9]{60,})\b")

# Generic high-confidence patterns
_add("private-key", "Private Key Block", r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?:\sBLOCK)?-----")
_add("database-url-password", "Database URL with Password",
     r"(?i)(?:mysql|postgres|postgresql|mongodb|redis)://[^:]+:([^@\s]{8,})@")

# Generic API key assignment (must have key= or key: context)
_add("generic-api-key-assignment", "Generic API Key Assignment",
     r"(?i)(?:api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token)\s*[=:]\s*['\"]([a-zA-Z0-9\-_./+=]{20,})['\"]")


def scan_for_secrets(content: str) -> list[SecretMatch]:
    """Scan content for potential secrets. Returns matches or empty list."""
    matches: list[SecretMatch] = []
    seen_rules: set[str] = set()

    for rule in _RULES:
        if rule.rule_id in seen_rules:
            continue
        if rule.pattern.search(content):
            matches.append(SecretMatch(rule_id=rule.rule_id, description=rule.description))
            seen_rules.add(rule.rule_id)

    return matches


def redact_secrets(content: str) -> str:
    """Replace detected secrets with [REDACTED]. For logging only."""
    result = content
    for rule in _RULES:
        result = rule.pattern.sub(f"[REDACTED:{rule.rule_id}]", result)
    return result
