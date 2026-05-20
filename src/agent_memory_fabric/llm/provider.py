"""LLM provider protocol and implementations."""

from __future__ import annotations

import json
from typing import Protocol


class LLMProvider(Protocol):
    """Abstract interface for LLM completions."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a completion. Returns the model's text response."""
        ...


class MockProvider:
    """Testing provider that returns configurable responses.

    Usage:
        mock = MockProvider(default_response="NO")
        mock.set_response_for("contradict", "YES: user moved to a new city")
    """

    def __init__(self, default_response: str = "NO"):
        self.default_response = default_response
        self._responses: list[str] = []
        self._keyword_responses: dict[str, str] = {}
        self.call_log: list[tuple[str, str]] = []

    def set_responses(self, responses: list[str]) -> None:
        """Set a queue of responses (consumed in order)."""
        self._responses = list(responses)

    def set_response_for(self, keyword: str, response: str) -> None:
        """Return specific response when user_prompt contains keyword."""
        self._keyword_responses[keyword.lower()] = response

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_log.append((system_prompt, user_prompt))

        for keyword, response in self._keyword_responses.items():
            if keyword in user_prompt.lower():
                return response

        if self._responses:
            return self._responses.pop(0)

        return self.default_response


class BedrockProvider:
    """AWS Bedrock provider using Claude models.

    Requires boto3 and valid AWS credentials.
    """

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        region: str = "us-east-1",
        max_tokens: int = 256,
    ):
        self.model_id = model_id
        self.region = region
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client("bedrock-runtime", region_name=self.region)
            except ImportError:
                raise ImportError("boto3 required. Install with: pip install boto3")
        return self._client

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_client()

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        })

        response = client.invoke_model(modelId=self.model_id, body=body)
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
