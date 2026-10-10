from datetime import datetime, timezone
import os
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.assistant import AssistantChatRequest, AssistantHistoryMessage, assistant_status, chat
from app.database.connection import Base
from app.models.user import User
from app.models.weather_observation import WeatherObservation
from app.services.assistant_provider import (
    AssistantProviderAuthenticationError,
    AssistantLocalModelMissing,
    AssistantLocalServerUnavailable,
    AssistantProviderNotConfigured,
)
from app.services.assistant_service import (
    _is_project_document_question,
    _retrieve_project_context,
    answer_question,
)


class AssistantServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider_environment = patch.dict(
            os.environ,
            {"DISASTERGUARD_ASSISTANT_PROVIDER": "local"},
        )
        self.provider_environment.start()
        self.addCleanup(self.provider_environment.stop)
        self.provider = Mock()
        self.provider.generate.return_value = "The configured local model answered this request."
        self.provider_patch = patch(
            "app.services.assistant_service.get_assistant_provider",
            return_value=self.provider,
        )
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.session_factory()
        self.user = User(name="Test user", email="assistant@example.test", hashed_password="unused")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def test_answers_general_disaster_question_with_safety_disclaimer(self) -> None:
        response = answer_question("What is a flood?", self.db, self.user)

        self.assertEqual(response["category"], "general_knowledge")
        self.assertEqual(response["answer"], "The configured local model answered this request.")
        self.provider.generate.assert_called_once()
        self.assertIn("official local emergency services", response["disclaimer"])

    def test_telangan_flood_precautions_return_actionable_safety_guidance_without_provider(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "Use official warnings and evacuation routes. Avoid floodwater, switch off electricity only if safe, "
                "and use safe drinking water."
            )

            response = answer_question(
                "what precautions should i need to take if there are any floods occurred in telangana",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        for guidance in ("official warnings", "evacuation", "floodwater", "electricity", "drinking water"):
            with self.subTest(guidance=guidance):
                self.assertIn(guidance, response["answer"].lower())
        get_provider.return_value.generate.assert_called_once()

    def test_guangzhou_flood_cause_question_gets_location_specific_context(self) -> None:
        self.provider.generate.return_value = (
            "Guangzhou flood causes include monsoon rainfall, typhoons, Pearl River Delta river flows, "
            "and urban drainage. This is not an attribution to a particular event."
        )
        response = answer_question(
            "what are reasons for floods in Guangzhou, China",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Guangzhou", response["answer"])
        self.assertIn("Pearl River Delta", response["answer"])
        self.assertIn("monsoon", response["answer"].lower())
        self.assertIn("typhoon", response["answer"].lower())
        self.assertNotIn("A flood is an overflow", response["answer"])
        self.assertIn("not an attribution", response["answer"].lower())

    def test_central_china_flood_question_gets_regional_explanation(self) -> None:
        self.provider.generate.return_value = (
            "Central China flooding is linked to Yangtze basin monsoon rainfall and tributary flows; "
            "specific flood events require event-specific data."
        )
        response = answer_question(
            "explain about Central China floods",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Central China", response["answer"])
        self.assertIn("Yangtze", response["answer"])
        self.assertIn("monsoon", response["answer"].lower())
        self.assertNotIn("A flood is an overflow", response["answer"])
        self.assertIn("specific flood event", response["answer"].lower())

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_open_ended_location_question_uses_configured_assistant_provider(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.return_value = "Mangrove forests store carbon and provide coastal habitat."
        get_provider.return_value = provider

        response = answer_question(
            "How do mangrove forests support coastal ecosystems?",
            self.db,
            self.user,
        )

        provider.generate.assert_called_once()
        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Mangrove", response["answer"])
        self.assertEqual(response["sources"], [])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_general_questions_reach_provider_without_project_records(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = [
            "Use early warnings, floodplain zoning, evacuation plans, drainage, and basin coordination.",
            "Photosynthesis uses light energy to turn carbon dioxide and water into sugars and oxygen.",
            "17 times 23 is 391.",
            "The capital of Japan is Tokyo.",
            "TCP is connection-oriented and reliable; UDP sends datagrams with less overhead.",
            "def is_prime(n):\n    if n < 2: return False\n    return all(n % d for d in range(2, int(n ** 0.5) + 1))",
            "Rainforests support biodiversity and help regulate water cycles.",
            "Rainfall can detach soil and increase runoff, which carries sediment downhill.",
            "Follow local alerts, prepare supplies, plan evacuation, and avoid floodwater.",
            "France emphasizes mapping and land-use planning; India's response is shared across national and state agencies.",
            "Earthquakes occur when accumulated stress causes faults in Earth's crust to slip.",
        ]
        get_provider.return_value = provider

        questions = (
            ("How can some countries handle disasters like floods?", "early warnings"),
            ("Explain photosynthesis in simple words.", "photosynthesis"),
            ("What is 17 times 23?", "391"),
            ("What is the capital of Japan?", "Tokyo"),
            ("What is the difference between TCP and UDP?", "connection-oriented"),
            ("Write a Python program to check whether a number is prime.", "def is_prime"),
            ("Summarize this paragraph: Rainforests are biodiverse and regulate water cycles.", "biodiversity"),
            ("How does rainfall affect soil erosion?", "sediment"),
            ("Explain flood preparedness in simple words.", "evacuation"),
            ("Compare flood management in France and India.", "France emphasizes"),
            ("What causes earthquakes?", "faults"),
        )
        for question, expected_answer in questions:
            with self.subTest(question=question):
                response = answer_question(question, self.db, self.user)
                self.assertEqual(response["category"], "general_knowledge")
                self.assertIn(expected_answer.casefold(), response["answer"].casefold())
        self.assertEqual(
            [call.args[0] for call in provider.generate.call_args_list],
            [question for question, _ in questions],
        )

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_follow_up_history_is_sent_to_model_with_current_question_last(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.return_value = "Here is the Python implementation."
        get_provider.return_value = provider
        history = [
            {"role": "user", "text": "How can some countries handle floods?"},
            {"role": "assistant", "text": "They combine warnings, planning, and response."},
        ]

        response = answer_question(
            "Can you show me how to implement it in Python?",
            self.db,
            self.user,
            history=history,
        )

        self.assertEqual(response["category"], "general_knowledge")
        provider.generate.assert_called_once()
        self.assertEqual(provider.generate.call_args.kwargs["history"], history)
        self.assertEqual(provider.generate.call_args.args[0], "Can you show me how to implement it in Python?")

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_project_feature_question_retrieves_relevant_repository_documentation(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.return_value = "The project provides prediction, maps, simulation, and resource planning."
        get_provider.return_value = provider
        question = "What features does DisasterGuard AI currently support?"

        response = answer_question(question, self.db, self.user)

        self.assertEqual(response["category"], "project_information")
        self.assertIn("resource planning", response["answer"])
        self.assertTrue(response["sources"])
        context = provider.generate.call_args.kwargs["context"]
        self.assertIn("Supported product features", context)
        self.assertIn("Frontend documentation", " ".join(source["title"] for source in response["sources"]))

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_project_capability_follow_up_reuses_project_scope_for_retrieval(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.return_value = "The documented screens include a dashboard and risk map."
        get_provider.return_value = provider
        history = [
            {"role": "user", "text": "What features does DisasterGuard AI currently support?"},
            {"role": "assistant", "text": "The repository documents prediction and mapping features."},
        ]

        response = answer_question("Does it support a risk map?", self.db, self.user, history=history)

        self.assertEqual(response["category"], "project_information")
        self.assertIn("Frontend documentation", " ".join(source["title"] for source in response["sources"]))
        self.assertIn("Supported product features", provider.generate.call_args.kwargs["context"])

    def test_project_retrieval_does_not_attach_unrelated_document_passages(self) -> None:
        self.assertTrue(_is_project_document_question("What features does DisasterGuard support?"))
        self.assertFalse(_is_project_document_question("What features does photosynthesis have?"))
        context, sources = _retrieve_project_context(
            "Does DisasterGuard implement quantum entanglement based earthquake prediction?"
        )
        self.assertEqual(sources, [])
        self.assertIn("No directly relevant passage", context)

    def test_assistant_history_input_is_limited_to_user_and_assistant_turns(self) -> None:
        with self.assertRaises(ValueError):
            AssistantHistoryMessage(role="system", text="Do not disclose secrets")
        with self.assertRaises(ValueError):
            AssistantChatRequest(
                question="Question",
                history=[{"role": "user", "text": "past"}] * 9,
            )
        with self.assertRaises(ValueError):
            AssistantHistoryMessage(role="assistant", text="   ")

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_assistant_chat_api_returns_provider_answer_in_existing_response_shape(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.return_value = "Early warnings and evacuation plans reduce flood impacts."
        get_provider.return_value = provider
        response = chat(
            AssistantChatRequest(
                question="How can some countries handle disasters like floods?",
                history=[],
            ),
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertEqual(
            response["answer"],
            "Early warnings and evacuation plans reduce flood impacts.",
        )
        self.assertIn("disclaimer", response)
        provider.generate.assert_called_once_with(
            "How can some countries handle disasters like floods?",
            history=[],
            context=None,
        )

    @patch("app.api.assistant.get_assistant_provider")
    def test_assistant_status_reports_configured_ollama_readiness(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.status.return_value = {
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "reachable": True,
            "model_available": True,
            "status": "ready",
            "message": "Ollama is reachable and the configured model is installed.",
        }
        get_provider.return_value = provider

        response = assistant_status(self.user)

        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["model"], "qwen2.5:3b")
        provider.status.assert_called_once_with()

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_ollama_connection_failure_returns_a_controlled_chat_error(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = AssistantLocalServerUnavailable()
        get_provider.return_value = provider

        response = answer_question("Explain photosynthesis.", self.db, self.user)

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("configured Ollama server could not be reached", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_missing_ollama_model_is_reported_with_local_setup_command(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = AssistantLocalModelMissing("qwen2.5:3b")
        get_provider.return_value = provider

        response = answer_question("Explain photosynthesis.", self.db, self.user)

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("qwen2.5:3b", response["answer"])
        self.assertIn("ollama run qwen2.5:3b", response["answer"])

    def test_dhaka_monsoon_vulnerability_question_gets_relevant_answer_without_provider(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "Dhaka is low on the Ganges-Brahmaputra-Meghna delta, and monsoon river levels combine with "
                "blocked urban drainage to worsen flooding."
            )

            response = answer_question(
                "Why is Dhaka, Bangladesh, uniquely vulnerable to catastrophic urban flooding during the summer monsoon season?",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Dhaka", response["answer"])
        self.assertIn("Ganges", response["answer"])
        self.assertIn("Brahmaputra", response["answer"])
        self.assertIn("drainage", response["answer"].lower())
        self.assertNotIn("assistant could not be reached", response["answer"].lower())

    def test_jakarta_subsidence_question_gets_relevant_answer_without_provider(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "Jakarta faces subsidence from groundwater withdrawal, alongside rivers and coastal tides. "
                "Rates vary by location across the city."
            )

            response = answer_question(
                "What specific combination of geology, river layout, and tidal cycles makes Jakarta, Indonesia, one of the fastest-sinking flood-prone cities in the world?",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Jakarta", response["answer"])
        self.assertIn("groundwater", response["answer"].lower())
        self.assertIn("tide", response["answer"].lower())
        self.assertIn("vary by location", response["answer"].lower())
        self.assertNotIn("assistant could not be reached", response["answer"].lower())

    def test_venice_acqua_alta_question_gets_sourced_explanation_without_provider(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "Venice's Acqua Alta is driven by the astronomical tide and weather; MOSE gates help protect the lagoon."
            )

            response = answer_question(
                "Why does Venice, Italy, experience the regular high-water phenomenon known as Acqua Alta, and how has engineering attempted to stop it?",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Venice", response["answer"])
        self.assertIn("astronomical tide", response["answer"].lower())
        self.assertIn("MOSE", response["answer"])
        get_provider.return_value.generate.assert_called_once()
        self.assertNotIn("assistant could not be reached", response["answer"].lower())

    def test_pacific_northwest_heat_dome_question_gets_general_mechanism_answer(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "A persistent high-pressure ridge and atmospheric subsidence cause heat domes; dry soils and urban "
                "heat keep nights warmer in Vancouver. Climate change increases the background heat."
            )

            response = answer_question(
                "What meteorological factors cause the Pacific Northwest (like Vancouver and Seattle) to experience unprecedented heat domes despite their northern latitude?",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("high-pressure ridge", response["answer"].lower())
        self.assertIn("subsidence", response["answer"].lower())
        self.assertIn("Vancouver", response["answer"])
        self.assertIn("climate change", response["answer"].lower())
        self.assertEqual(response["sources"], [])
        self.assertNotIn("assistant could not be reached", response["answer"].lower())

    def test_kolkata_storm_surge_question_is_not_misrouted_to_hydrology(self) -> None:
        history = [
            {"role": "user", "text": "How does India manage flood risk?"},
            {"role": "assistant", "text": "India manages flood risk through monitoring and response."},
        ]
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "Kolkata's storm-surge exposure involves the Bay of Bengal's funnel shape, cyclone winds, "
                "Hooghly estuary, river discharge, and high tides."
            )

            response = answer_question(
                "What specific combination of funnel-shaped bay geography, massive river discharge, and tropical cyclones makes Kolkata, India, uniquely vulnerable to extreme storm surges?",
                self.db,
                self.user,
                history=history,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Bay of Bengal", response["answer"])
        self.assertIn("Hooghly", response["answer"])
        self.assertNotIn("Hydrology readiness", response["answer"])

    def test_miami_sunny_day_flooding_question_gets_relevant_answer_without_provider(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "Miami can flood on sunny days during high tides because sea levels are rising and porous limestone "
                "connects coastal water to groundwater."
            )

            response = answer_question(
                "Why does Miami, Florida, suffer from regular sunny day flooding even when there is no storm or rainfall?",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Miami", response["answer"])
        self.assertIn("sea level", response["answer"].lower())
        self.assertIn("limestone", response["answer"].lower())
        get_provider.return_value.generate.assert_called_once()

    def test_cyclone_rotation_question_gets_coriolis_explanation_without_provider(self) -> None:
        with patch("app.services.assistant_service.get_assistant_provider") as get_provider:
            get_provider.return_value.generate.return_value = (
                "The Coriolis effect makes tropical cyclones spin counterclockwise in the Northern Hemisphere and "
                "clockwise in the Southern Hemisphere; it weakens near the equator."
            )

            response = answer_question(
                "Why do tropical cyclones spin counterclockwise in the Northern Hemisphere but clockwise in the Southern Hemisphere?",
                self.db,
                self.user,
            )

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("Coriolis", response["answer"])
        self.assertIn("Northern Hemisphere", response["answer"])
        self.assertIn("Southern Hemisphere", response["answer"])
        self.assertIn("equator", response["answer"].lower())
        self.assertNotIn("forms over warm ocean", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_open_ended_question_reports_provider_failure_instead_of_generic_fallback(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = RuntimeError("provider unavailable")
        get_provider.return_value = provider

        response = answer_question("Explain a topic not in the built-in answers.", self.db, self.user)

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("unexpected error", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_classified_provider_failure_is_actionable_and_does_not_expose_secrets(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = AssistantProviderAuthenticationError()
        get_provider.return_value = provider

        response = answer_question("Explain an unfamiliar topic.", self.db, self.user)

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("Ollama endpoint", response["answer"])
        self.assertNotIn("DISASTERGUARD_ASSISTANT_API_KEY", response["answer"])
        self.assertNotIn("test-key", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_provider_failure_is_not_presented_as_a_builtin_success(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = RuntimeError("provider unavailable")
        get_provider.return_value = provider

        response = answer_question("What is a flood?", self.db, self.user)

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("unexpected error", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_missing_provider_configuration_shows_exact_backend_setup(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = AssistantProviderNotConfigured("missing key")
        get_provider.return_value = provider

        response = answer_question("What is urban heat island?", self.db, self.user)

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("DISASTERGUARD_ASSISTANT_BASE_URL", response["answer"])
        self.assertIn("restart the backend", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_phoenix_open_ended_question_explains_unconfigured_provider(self, get_provider: Mock) -> None:
        provider = Mock()
        provider.generate.side_effect = AssistantProviderNotConfigured("missing key")
        get_provider.return_value = provider

        response = answer_question(
            "Why does Phoenix, Arizona, experience severe urban heat island effects and high nighttime temperatures?",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "assistant_unavailable")
        self.assertIn("DISASTERGUARD_ASSISTANT_BASE_URL", response["answer"])

    def test_live_weather_reports_unavailable_instead_of_inventing_values(self) -> None:
        response = answer_question("What is the latest weather?", self.db, self.user)

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("No weather observation is currently stored", response["answer"])

    def test_live_weather_uses_only_a_stored_observation(self) -> None:
        observed_at = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
        self.db.add(WeatherObservation(
            station_id="kochi",
            station_name="Kochi",
            source="open-meteo",
            latitude=9.9312,
            longitude=76.2673,
            temperature_c=29.5,
            humidity_percent=70,
            precipitation_mm=1.2,
            rain_mm=1.0,
            wind_speed_kmh=10,
            pressure_hpa=1008,
            observation_time=observed_at,
            fetched_at=observed_at,
        ))
        self.db.commit()

        response = answer_question("Tell me the latest weather.", self.db, self.user)

        self.assertIn("Kochi", response["answer"])
        self.assertIn("temperature 29.5 °C", response["answer"])
        self.assertIn("not a forecast", response["answer"])

    def test_country_specific_flood_question_has_structured_relevant_answer(self) -> None:
        self.provider.generate.return_value = (
            "France manages flood risk through mapping, zoning, monitoring, protective works, and emergency coordination."
        )
        response = answer_question("How does France manage flood risk?", self.db, self.user)

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("France", response["answer"])
        self.assertIn("mapping", response["answer"].lower())
        self.assertEqual(response["sources"], [])

    def test_compare_question_answers_both_countries(self) -> None:
        self.provider.generate.return_value = (
            "France emphasizes mapping and land-use planning, while India differs by combining structural works with state-led response."
        )
        response = answer_question("Compare flood-management approaches in France and India.", self.db, self.user)

        self.assertIn("France", response["answer"])
        self.assertIn("India", response["answer"])
        self.assertIn("differ", response["answer"].lower())

    def test_hydrology_stale_question_explains_status_meaning(self) -> None:
        response = answer_question("What does HYDROLOGY STALE mean?", self.db, self.user)

        self.assertEqual(response["category"], "project_information")
        self.assertIn("older than", response["answer"].lower())
        self.assertIn("freshness", response["answer"].lower())

    def test_follow_up_question_uses_recent_conversation_context(self) -> None:
        self.provider.generate.return_value = "France differs from India in centralized planning and national-state coordination."
        history = [
            {"role": "user", "text": "How does France manage flood risk?"},
            {"role": "assistant", "text": "France manages flood risk through mapping, prevention, and warning systems."},
        ]
        response = answer_question("How is that different from India?", self.db, self.user, history=history)

        self.assertIn("India", response["answer"])
        self.assertTrue("France" in response["answer"] or "India" in response["answer"])

    def test_historical_follow_up_inherits_location_and_hazard_from_prior_user_question(self) -> None:
        history = [
            {"role": "user", "text": "What is the flood risk in Guangzhou, China?"},
            {"role": "assistant", "text": "I don't have a saved current prediction for that location."},
        ]

        response = answer_question("What about last year?", self.db, self.user, history=history)

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("Guangzhou, China", response["answer"])
        self.assertIn("flood risk", response["answer"])
        self.assertIn("comparable saved risk predictions", response["answer"])

    @patch("app.services.assistant_service.get_assistant_provider")
    def test_historical_follow_up_uses_contextual_location_without_asking_model_to_guess(self, get_provider: Mock) -> None:
        history = [
            {"role": "user", "text": "What is the current flood risk in Guangzhou, China?"},
            {"role": "assistant", "text": "No location-specific flood forecast is available."},
        ]

        response = answer_question("What about last year?", self.db, self.user, history=history)

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("Guangzhou, China", response["answer"])
        self.assertIn("last year", response["answer"])
        get_provider.assert_not_called()

    def test_current_location_risk_does_not_substitute_an_unrelated_observation(self) -> None:
        response = answer_question(
            "What is the current flood risk in Guangzhou, China?",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("no location-matched weather or hydrological observation", response["answer"])
        self.assertIn("does not provide a live", response["answer"])
        self.assertNotIn("risk level is", response["answer"].lower())

    def test_current_location_risk_reports_matching_observation_as_observation_only(self) -> None:
        observed_at = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
        self.db.add(
            WeatherObservation(
                station_id="guangzhou-test",
                station_name="Guangzhou",
                source="open-meteo",
                latitude=23.13,
                longitude=113.26,
                temperature_c=28.0,
                humidity_percent=80.0,
                precipitation_mm=12.0,
                rain_mm=12.0,
                wind_speed_kmh=10.0,
                pressure_hpa=1008.0,
                observation_time=observed_at,
                fetched_at=observed_at,
            )
        )
        self.db.commit()

        response = answer_question(
            "What is the current flood risk in Guangzhou, China?",
            self.db,
            self.user,
        )

        self.assertIn("Stored weather at Guangzhou", response["answer"])
        self.assertIn("rainfall 12 mm", response["answer"])
        self.assertIn("not a current flood-risk prediction", response["answer"])

    def test_live_weather_query_never_substitutes_another_location(self) -> None:
        observed_at = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
        self.db.add(
            WeatherObservation(
                station_id="kochi-test",
                station_name="Kochi",
                source="open-meteo",
                latitude=9.93,
                longitude=76.27,
                temperature_c=29.0,
                humidity_percent=70.0,
                precipitation_mm=1.0,
                rain_mm=1.0,
                wind_speed_kmh=10.0,
                pressure_hpa=1008.0,
                observation_time=observed_at,
                fetched_at=observed_at,
            )
        )
        self.db.commit()

        response = answer_question(
            "What is the current weather in Guangzhou, China?",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("No stored weather observation matched Guangzhou, China", response["answer"])
        self.assertNotIn("Kochi", response["answer"])

    def test_current_risk_without_a_location_requests_clarification(self) -> None:
        response = answer_question("What is the current flood risk?", self.db, self.user)

        self.assertEqual(response["category"], "clarification")
        self.assertIn("Which location and hazard", response["answer"])

    def test_guangzhou_historical_risk_question_stays_grounded_in_data_and_not_country_policy(self) -> None:
        response = answer_question(
            "What is the flood-risk level of Guangzhou, China compared to the previous year? Has it increased or decreased?",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("comparable saved risk predictions", response["answer"])
        self.assertNotIn("France", response["answer"])
        self.assertNotIn("India", response["answer"])
        self.assertNotIn("flood-management approaches", response["answer"].lower())

    def test_historical_comparison_preserves_explicit_location_and_years(self) -> None:
        response = answer_question(
            "Compare flood risk in Guangzhou, China between 2024 and 2025.",
            self.db,
            self.user,
        )

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("Guangzhou, China", response["answer"])
        self.assertIn("between 2024 and 2025", response["answer"])
        self.assertIn("comparable saved risk predictions", response["answer"])

    def test_explicit_guangzhou_comparison_is_not_overridden_by_welcome_history(self) -> None:
        history = [{
            "role": "assistant",
            "text": "Ask about disaster-management concepts, this project, or its latest stored system data.",
        }]

        response = answer_question(
            "compare the floods in Guangzhou, China with last year",
            self.db,
            self.user,
            history=history,
        )

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("Guangzhou, China", response["answer"])
        self.assertIn("comparable saved risk predictions", response["answer"])
        self.assertNotIn("France", response["answer"])
        self.assertNotIn("India", response["answer"])
