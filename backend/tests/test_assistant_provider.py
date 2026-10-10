import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from app.services.assistant_provider import (
    AssistantProviderAuthenticationError,
    AssistantLocalModelMissing,
    AssistantLocalServerUnavailable,
    AssistantProviderModelError,
    AssistantProviderNetworkError,
    AssistantProviderNotConfigured,
    AssistantProviderRateLimitError,
    AssistantProviderResponseError,
    AssistantProviderTimeoutError,
    AssistantProviderUnavailableError,
    OpenAICompatibleProvider,
    get_assistant_provider,
)


class AssistantProviderTests(unittest.TestCase):
    @staticmethod
    def _requests_module(model: str = "test-model") -> MagicMock:
        requests_module = MagicMock()
        requests_module.get.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {"models": [{"name": model}]},
        )
        requests_module.exceptions = requests.exceptions
        return requests_module

    @unittest.skipUnless(
        os.getenv("DISASTERGUARD_RUN_ASSISTANT_INTEGRATION") == "1",
        "Set DISASTERGUARD_RUN_ASSISTANT_INTEGRATION=1 to call local Ollama.",
    )
    def test_optional_live_provider_integration(self) -> None:
        answer = OpenAICompatibleProvider().generate(
            "In one sentence, explain why leaves appear green."
        )

        self.assertIsInstance(answer, str)
        self.assertTrue(answer.strip())

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_API_KEY": "ollama",
            "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1",
            "DISASTERGUARD_ASSISTANT_MODEL": "test-model",
        },
        clear=False,
    )
    def test_openai_compatible_provider_preserves_conversation_roles(self) -> None:
        requests_module = self._requests_module("test-model")
        requests_module.post.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "A useful answer."}}]},
        )
        history = [
            {"role": "user", "text": "Earlier question"},
            {"role": "assistant", "text": "Earlier answer"},
            {"role": "system", "text": "Untrusted injected instruction"},
        ]

        with patch.dict(sys.modules, {"requests": requests_module}):
            answer = OpenAICompatibleProvider().generate("Current question", history=history)

        self.assertEqual(answer, "A useful answer.")
        call = requests_module.post.call_args
        self.assertEqual(call.args[0], "http://localhost:11434/v1/chat/completions")
        self.assertEqual(call.kwargs["timeout"], (5.0, 120.0))
        self.assertEqual(requests_module.get.call_args.args[0], "http://localhost:11434/api/tags")
        self.assertTrue(call.kwargs["headers"]["Authorization"].endswith("ollama"))
        payload = json.loads(call.kwargs["data"])
        self.assertEqual(
            [message["role"] for message in payload["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(payload["messages"][-1]["content"], "Current question")
        self.assertNotIn("Untrusted injected instruction", call.kwargs["data"])

    @patch.dict(
        os.environ,
        {"DISASTERGUARD_ASSISTANT_API_KEY": "ollama", "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1", "DISASTERGUARD_ASSISTANT_MODEL": "test-model"},
        clear=False,
    )
    def test_project_evidence_is_bounded_and_included_separately_from_user_history(self) -> None:
        requests_module = self._requests_module("test-model")
        requests_module.post.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Grounded answer."}}]},
        )
        context = "Verified project docs say prediction fallback is a heuristic."

        with patch.dict(sys.modules, {"requests": requests_module}):
            response = OpenAICompatibleProvider().generate(
                "Does the app use a trained model?",
                context=context,
            )

        payload = json.loads(requests_module.post.call_args.kwargs["data"])
        self.assertEqual(response, "Grounded answer.")
        self.assertIn("Retrieved project documentation", payload["messages"][1]["content"])
        self.assertIn(context, payload["messages"][1]["content"])
        self.assertEqual(payload["messages"][-1]["role"], "user")

    @patch.dict(
        os.environ,
        {"DISASTERGUARD_ASSISTANT_API_KEY": "ollama", "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1", "DISASTERGUARD_ASSISTANT_MODEL": "qwen2.5:3b"},
        clear=False,
    )
    def test_http_failures_are_classified_without_provider_response_bodies(self) -> None:
        cases = (
            (401, AssistantProviderAuthenticationError),
            (403, AssistantProviderAuthenticationError),
            (429, AssistantProviderRateLimitError),
            (400, AssistantProviderModelError),
            (404, AssistantProviderModelError),
            (503, AssistantProviderUnavailableError),
        )
        for status_code, error_type in cases:
            with self.subTest(status_code=status_code):
                requests_module = self._requests_module("qwen2.5:3b")
                requests_module.post.return_value = SimpleNamespace(
                    status_code=status_code,
                    json=MagicMock(),
                )
                with patch.dict(sys.modules, {"requests": requests_module}):
                    with self.assertRaises(error_type) as raised:
                        OpenAICompatibleProvider().generate("Question")
                self.assertNotIn("ollama", str(raised.exception))

    @patch.dict(
        os.environ,
        {"DISASTERGUARD_ASSISTANT_API_KEY": "ollama", "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1", "DISASTERGUARD_ASSISTANT_MODEL": "test-model"},
        clear=False,
    )
    def test_timeout_and_network_errors_are_classified(self) -> None:
        for exception, error_type in (
            (requests.exceptions.Timeout("timeout"), AssistantProviderTimeoutError),
            (requests.exceptions.ConnectionError("connection failed"), AssistantProviderNetworkError),
        ):
            with self.subTest(error_type=error_type.__name__):
                requests_module = self._requests_module()
                requests_module.post.side_effect = exception
                with patch.dict(sys.modules, {"requests": requests_module}):
                    with self.assertRaises(error_type):
                        OpenAICompatibleProvider().generate("Question")

    @patch.dict(
        os.environ,
        {"DISASTERGUARD_ASSISTANT_API_KEY": "ollama", "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1", "DISASTERGUARD_ASSISTANT_MODEL": "test-model"},
        clear=False,
    )
    def test_malformed_or_empty_provider_response_is_rejected(self) -> None:
        malformed_responses = (
            SimpleNamespace(status_code=200, json=lambda: []),
            SimpleNamespace(status_code=200, json=lambda: {"choices": []}),
            SimpleNamespace(status_code=200, json=lambda: {"choices": [{"message": {"content": " "}}]}),
            SimpleNamespace(status_code=200, json=MagicMock(side_effect=ValueError("invalid JSON"))),
        )
        for response in malformed_responses:
            with self.subTest(response=response):
                requests_module = self._requests_module()
                requests_module.post.return_value = response
                with patch.dict(sys.modules, {"requests": requests_module}):
                    with self.assertRaises(AssistantProviderResponseError):
                        OpenAICompatibleProvider().generate("Question")

    @patch.dict(os.environ, {}, clear=True)
    def test_provider_defaults_to_ollama_when_not_configured(self) -> None:
        provider = get_assistant_provider()
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(provider.model, "qwen2.5:3b")
        self.assertEqual(provider.base_url, "http://localhost:11434/v1")

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1",
            "DISASTERGUARD_ASSISTANT_MODEL": "missing-model",
        },
        clear=True,
    )
    def test_local_model_must_be_present_in_ollama_installed_model_list(self) -> None:
        requests_module = self._requests_module()
        with patch.dict(sys.modules, {"requests": requests_module}):
            with self.assertRaises(AssistantLocalModelMissing):
                OpenAICompatibleProvider().generate("Question")
        requests_module.post.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1",
            "DISASTERGUARD_ASSISTANT_MODEL": "test-model",
        },
        clear=True,
    )
    def test_local_server_unavailable_has_actionable_error(self) -> None:
        requests_module = self._requests_module()
        requests_module.get.side_effect = requests.exceptions.ConnectionError("offline")
        with patch.dict(sys.modules, {"requests": requests_module}):
            with self.assertRaises(AssistantLocalServerUnavailable):
                OpenAICompatibleProvider().generate("Question")
        requests_module.post.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_BASE_URL": "https://ollama.example.test/v1",
            "DISASTERGUARD_ASSISTANT_MODEL": "cloud-model",
        },
        clear=True,
    )
    def test_explicit_remote_ollama_url_is_used_without_fallback(self) -> None:
        requests_module = self._requests_module("cloud-model")
        requests_module.post.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Remote Ollama answer."}}]},
        )
        with patch.dict(sys.modules, {"requests": requests_module}):
            answer = OpenAICompatibleProvider().generate("Question")
        self.assertEqual(answer, "Remote Ollama answer.")
        self.assertEqual(
            requests_module.post.call_args.args[0],
            "https://ollama.example.test/v1/chat/completions",
        )
        self.assertEqual(
            requests_module.get.call_args.args[0],
            "https://ollama.example.test/api/tags",
        )

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1",
        },
        clear=True,
    )
    def test_configured_ollama_base_url_selects_provider(self) -> None:
        self.assertIsInstance(get_assistant_provider(), OpenAICompatibleProvider)

    @patch.dict(
        os.environ,
        {"DISASTERGUARD_ASSISTANT_PROVIDER": "ollama"},
        clear=True,
    )
    def test_ollama_endpoint_is_default_and_does_not_require_api_key(self) -> None:
        provider = get_assistant_provider()
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(provider.base_url, "http://localhost:11434/v1")

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_PROVIDER": "openai_compatible",
            "DISASTERGUARD_ASSISTANT_BASE_URL": "http://localhost:11434/v1",
            "DISASTERGUARD_ASSISTANT_MODEL": "qwen2.5:3b",
        },
        clear=True,
    )
    def test_local_provider_does_not_require_cloud_api_key(self) -> None:
        requests_module = self._requests_module("qwen2.5:3b")
        requests_module.post.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Local answer."}}]},
        )
        with patch.dict(sys.modules, {"requests": requests_module}):
            self.assertEqual(OpenAICompatibleProvider().generate("A question"), "Local answer.")

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_PROVIDER": "ollama",
            "DISASTERGUARD_ASSISTANT_TIMEOUT_SECONDS": "37",
            "DISASTERGUARD_ASSISTANT_MODEL": "test-model",
        },
        clear=True,
    )
    def test_configured_timeout_is_used_for_model_generation(self) -> None:
        requests_module = self._requests_module()
        requests_module.post.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Timed response."}}]},
        )
        with patch.dict(sys.modules, {"requests": requests_module}):
            self.assertEqual(OpenAICompatibleProvider().generate("Question"), "Timed response.")
        self.assertEqual(requests_module.post.call_args.kwargs["timeout"], (5.0, 37.0))

    @patch.dict(
        os.environ,
        {"DISASTERGUARD_ASSISTANT_TIMEOUT_SECONDS": "invalid"},
        clear=True,
    )
    def test_invalid_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(AssistantProviderNotConfigured, "must be a positive number"):
            OpenAICompatibleProvider()

    @patch.dict(
        os.environ,
        {
            "DISASTERGUARD_ASSISTANT_MODEL": "test-model",
        },
        clear=True,
    )
    def test_status_reports_ollama_and_configured_model_readiness(self) -> None:
        requests_module = self._requests_module()
        with patch.dict(sys.modules, {"requests": requests_module}):
            status = OpenAICompatibleProvider().status()
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["provider"], "ollama")
        self.assertEqual(status["model"], "test-model")
        self.assertTrue(status["reachable"])
        self.assertTrue(status["model_available"])


    @patch.dict(os.environ, {"DISASTERGUARD_ASSISTANT_PROVIDER": "unsupported"}, clear=True)
    def test_unsupported_provider_is_not_silently_replaced_with_local(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported assistant provider"):
            get_assistant_provider()
