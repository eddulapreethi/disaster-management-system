from __future__ import annotations

import json
import os
from typing import Any


class AssistantProvider:
    """Interface for optional LLM-backed answer generation."""

    def generate(self, question: str, *, history: list[dict[str, Any]] | None = None) -> str:
        raise NotImplementedError


class LocalAssistantProvider(AssistantProvider):
    def generate(self, question: str, *, history: list[dict[str, Any]] | None = None) -> str:
        return ""


class OpenAICompatibleProvider(AssistantProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("DISASTERGUARD_ASSISTANT_API_KEY", "").strip()
        self.base_url = os.getenv("DISASTERGUARD_ASSISTANT_BASE_URL", "").strip()
        self.model = os.getenv("DISASTERGUARD_ASSISTANT_MODEL", "gpt-4o-mini").strip()

    def generate(self, question: str, *, history: list[dict[str, Any]] | None = None) -> str:
        if not self.api_key or not self.base_url:
            raise RuntimeError("Assistant provider is not configured.")

        try:
            import requests
        except ImportError as exc:  # pragma: no cover - optional dependency check.
            raise RuntimeError("The requests package is required for remote assistant providers.") from exc

        messages = [{"role": "user", "content": question}]
        if history:
            messages = [
                {"role": "user", "content": item.get("text", "")}
                for item in history[-6:]
                if item.get("role") == "user"
            ] + [{"role": "user", "content": question}]
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": "You are a careful disaster-management assistant for DisasterGuard AI. Answer only with truthful, non-emergency guidance. Explicitly distinguish facts from project data and never fabricate sources or values."}, *[ {"role": "user", "content": item["content"]} for item in messages ]],
            "temperature": 0.2,
        }
        response = requests.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
            data=json.dumps(payload),
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Assistant provider returned no choices.")
        return choices[0]["message"]["content"].strip()


def get_assistant_provider() -> AssistantProvider:
    provider_name = os.getenv("DISASTERGUARD_ASSISTANT_PROVIDER", "local").strip().lower()
    if provider_name == "openai_compatible":
        return OpenAICompatibleProvider()
    return LocalAssistantProvider()
