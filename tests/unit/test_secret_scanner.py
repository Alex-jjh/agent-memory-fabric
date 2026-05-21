"""Tests for secret scanner."""

import pytest

from agent_memory_fabric.core.secret_scanner import (
    SecretDetectedError,
    SecretMatch,
    redact_secrets,
    scan_for_secrets,
)


class TestScanForSecrets:
    def test_clean_content_passes(self):
        assert scan_for_secrets("User prefers dark mode in editors") == []

    def test_clean_code_no_false_positive(self):
        code = '''
def compute_hash(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()
'''
        assert scan_for_secrets(code) == []

    def test_aws_access_key(self):
        content = "My key is AKIAIOSFODNN7EXAMPLE"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.rule_id == "aws-access-key-id" for m in matches)

    def test_github_pat(self):
        content = "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "github-pat" for m in matches)

    def test_github_fine_grained(self):
        content = "github_pat_" + "A" * 82
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "github-fine-grained-pat" for m in matches)

    def test_gitlab_pat(self):
        content = "token = glpat-ABCDEFGHIJKLMNOPQRSTx"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "gitlab-pat" for m in matches)

    def test_slack_bot_token(self):
        # Assembled at runtime to avoid GitHub push protection
        token = "xoxb" + "-1234567890-1234567890-ABCDEFGHIJKLMNOPQRSTUVWx"
        content = f"SLACK_TOKEN={token}"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "slack-bot-token" for m in matches)

    def test_anthropic_api_key(self):
        content = "sk-ant-" + "a" * 80 + "bcd"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "anthropic-api-key" for m in matches)

    def test_stripe_secret_key(self):
        # Assembled at runtime to avoid GitHub push protection
        key = "sk_" + "live_ABCDEFGHIJKLMNOPQRSTUVWXyz"
        content = key
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "stripe-secret-key" for m in matches)

    def test_private_key_block(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "private-key" for m in matches)

    def test_gcp_api_key(self):
        content = "key: AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ1234567"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "gcp-api-key" for m in matches)

    def test_generic_api_key_assignment(self):
        content = 'api_key = "sk_test_abcdef1234567890abcdefgh"'
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "generic-api-key-assignment" for m in matches)

    def test_database_url_with_password(self):
        content = "DATABASE_URL=postgres://user:supersecretpassword@host:5432/db"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "database-url-password" for m in matches)

    def test_huggingface_token(self):
        content = "hf_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        matches = scan_for_secrets(content)
        assert any(m.rule_id == "huggingface-token" for m in matches)

    def test_multiple_secrets(self):
        content = "AKIAIOSFODNN7EXAMPLE and ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        matches = scan_for_secrets(content)
        assert len(matches) >= 2

    def test_no_duplicate_rule_matches(self):
        content = "AKIAIOSFODNN7EXAMPLE and AKIAIOSFODNN7EXAMPL2"
        matches = scan_for_secrets(content)
        aws_matches = [m for m in matches if m.rule_id == "aws-access-key-id"]
        assert len(aws_matches) == 1


class TestRedactSecrets:
    def test_redacts_key(self):
        content = "My AWS key is AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(content)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED:" in result

    def test_clean_content_unchanged(self):
        content = "Normal text with no secrets"
        assert redact_secrets(content) == content


class TestSecretDetectedError:
    def test_error_message(self):
        matches = [SecretMatch(rule_id="aws-access-key-id", description="AWS Access Key ID")]
        err = SecretDetectedError(matches)
        assert "AWS Access Key ID" in str(err)
        assert err.matches == matches


class TestEngineIntegration:
    def test_engine_rejects_secret(self):
        import tempfile
        from agent_memory_fabric.core.engine import MemoryEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            with pytest.raises(SecretDetectedError):
                engine.write(content="my token is ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")

    def test_engine_allows_clean_content(self):
        import tempfile
        from agent_memory_fabric.core.engine import MemoryEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            node = engine.write(content="User prefers dark mode in all editors")
            assert node is not None
